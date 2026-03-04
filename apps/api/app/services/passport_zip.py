from __future__ import annotations

import io
import json
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

import httpx

from app.api.evidence import get_download_url


@dataclass
class EvidenceZipResult:
    evidence_total: int
    evidence_downloaded: int
    evidence_failed: int
    freshness_counts: dict
    manifest_items: list[dict]


def _safe_zip_name(name: str, fallback: str) -> str:
    from pathlib import PurePosixPath
    import re

    base = PurePosixPath(name or "").name
    base = base.replace("..", ".")
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip()
    if not base:
        base = fallback
    return base[:120]


def _classify_http_error(ex: Exception) -> tuple[str, bool, int | None]:
    if isinstance(ex, httpx.TimeoutException):
        return "timeout", True, None
    if isinstance(ex, httpx.ConnectError):
        return "connect_error", True, None
    if isinstance(ex, httpx.RemoteProtocolError):
        return "protocol_error", True, None
    if isinstance(ex, httpx.HTTPStatusError):
        code = ex.response.status_code if ex.response is not None else None
        if code in (408, 429, 500, 502, 503, 504):
            return "http_transient", True, code
        return "http_fatal", False, code
    return "unknown_error", True, None


def build_passport_zip_bytes(
    *,
    template_code: str,
    tenant_id: str,
    pack: Dict[str, Any],
    docx_bytes: bytes,
    include_evidence: bool,
    http_timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> Tuple[bytes, EvidenceZipResult]:
    evidence_items: List[Dict[str, Any]] = (pack.get("evidence") or []) if include_evidence else []

    counts = {"fresh": 0, "expiring": 0, "expired": 0, "unknown": 0}
    for ev in evidence_items:
        s = (ev.get("freshness_status") or "unknown").strip().lower()
        if s not in counts:
            s = "unknown"
        counts[s] += 1

    failures: List[str] = []
    downloaded = 0
    manifest_items: List[dict] = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps(pack, indent=2, ensure_ascii=False))
        z.writestr("security_passport.docx", docx_bytes)

        if evidence_items:
            z.writestr("evidence/README.txt", "Evidence files attached to answers.\n")

            with httpx.Client(timeout=http_timeout_seconds) as client:
                for ev in evidence_items:
                    ev_id = ev.get("id", "")
                    storage_key = ev.get("storage_key")

                    if not storage_key:
                        failures.append(f"{ev_id} missing_storage_key")
                        manifest_items.append(
                            {
                                "evidence_id": ev_id,
                                "original_filename": ev.get("original_filename"),
                                "storage_key": None,
                                "zip_path": None,
                                "status": "skipped",
                                "reason": "missing_storage_key",
                            }
                        )
                        continue

                    orig = (ev.get("original_filename") or "").strip()
                    safe = _safe_zip_name(orig, f"{ev_id}.bin")
                    path_in_zip = f"evidence/files/{ev_id}_{safe}"

                    dl = get_download_url(storage_key)
                    url = dl["url"]

                    attempt = 0
                    last_ex: Exception | None = None
                    total = 0
                    while attempt < max_attempts:
                        attempt += 1
                        total = 0
                        try:
                            with client.stream("GET", url) as r:
                                r.raise_for_status()
                                with z.open(path_in_zip, "w") as w:
                                    for chunk in r.iter_bytes():
                                        if not chunk:
                                            continue
                                        total += len(chunk)
                                        w.write(chunk)

                            downloaded += 1
                            manifest_items.append(
                                {
                                    "evidence_id": ev_id,
                                    "original_filename": ev.get("original_filename"),
                                    "storage_key": storage_key,
                                    "zip_path": path_in_zip,
                                    "status": "downloaded",
                                    "bytes": total,
                                    "attempts": attempt,
                                }
                            )
                            last_ex = None
                            break

                        except Exception as ex:
                            last_ex = ex
                            err_type, retryable, http_status = _classify_http_error(ex)
                            if attempt >= max_attempts or not retryable:
                                failures.append(f"{ev_id} {safe} {type(ex).__name__}")
                                manifest_items.append(
                                    {
                                        "evidence_id": ev_id,
                                        "original_filename": ev.get("original_filename"),
                                        "storage_key": storage_key,
                                        "zip_path": path_in_zip,
                                        "status": "failed",
                                        "error_type": err_type,
                                        "http_status": http_status,
                                        "attempts": attempt,
                                        "error": f"{type(ex).__name__}: {str(ex)}",
                                    }
                                )
                                break
                            time.sleep(backoff_seconds * (2 ** (attempt - 1)))

            summary = {
                "template_code": template_code,
                "tenant_id": tenant_id,
                "generated_at": datetime.utcnow().isoformat(),
                "evidence_total": len(evidence_items),
                "evidence_downloaded": downloaded,
                "evidence_failed": len(failures),
                "freshness_counts": counts,
            }

            z.writestr(
                "evidence/_meta.txt",
                f"count={len(evidence_items)}\n"
                f"downloaded={downloaded}\n"
                f"failed={len(failures)}\n"
                f"fresh={counts.get('fresh',0)} expiring={counts.get('expiring',0)} "
                f"expired={counts.get('expired',0)} unknown={counts.get('unknown',0)}\n",
            )

            z.writestr(
                "evidence/meta.json",
                json.dumps({**summary, "items": manifest_items}, indent=2, ensure_ascii=False),
            )

            z.writestr(
                "evidence/meta.jsonl",
                "\n".join(json.dumps(x, ensure_ascii=False) for x in manifest_items) + "\n",
            )

    out_bytes = buf.getvalue()

    return out_bytes, EvidenceZipResult(
        evidence_total=len(evidence_items),
        evidence_downloaded=downloaded,
        evidence_failed=len(failures),
        freshness_counts=counts,
        manifest_items=manifest_items,
    )