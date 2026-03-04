import hashlib
import re
import uuid
from uuid import UUID
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
from uuid import uuid4
from app.core.queue import get_queue
from app.models.core import JobRun

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.core.settings import settings
from app.core.storage import s3_client
from app.core.tenant_overrides import get_overrides
from app.db.session import SessionLocal
from app.models.core import EvidenceItem


FRESHNESS_EXPIRING_DAYS = 14
ALLOWED_SOURCE_SYSTEMS = {"manual", "azure", "m365", "github", "aws", "gcp", "okta", "jira"}

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None

    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = datetime.fromisoformat(s)
            return d.replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"{field} must be ISO date (YYYY-MM-DD) or ISO datetime")

    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s

    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        raise ValueError(f"{field} must be ISO datetime (e.g. 2026-02-24T10:00:00Z)")

    if dt.tzinfo is None:
        raise ValueError(f"{field} must include timezone (Z or +00:00)")

    return dt.astimezone(timezone.utc)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    return _to_utc(dt)


def _age_days(item: EvidenceItem, now: datetime) -> int | None:
    base = _to_utc(getattr(item, "uploaded_at", None)) or _to_utc(getattr(item, "created_at", None))
    if base is None:
        return None
    nowu = _to_utc(now) or now
    return max(0, int((nowu - base).total_seconds() // 86400))


def _effective_expires_at(item: EvidenceItem, retention_days: int | None) -> datetime | None:
    explicit = _to_utc(getattr(item, "expires_at", None))

    computed: datetime | None = None
    if retention_days is not None and retention_days > 0:
        uploaded_at = _to_utc(getattr(item, "uploaded_at", None))
        if uploaded_at is not None:
            computed = uploaded_at + timedelta(days=retention_days)

    if explicit is None:
        return computed
    if computed is None:
        return explicit
    return explicit if explicit <= computed else computed


def _freshness_status(effective_expires_at: datetime | None, now: datetime, expiring_days: int) -> str:
    if effective_expires_at is None:
        return "unknown"
    if effective_expires_at <= now:
        return "expired"
    if effective_expires_at <= (now + timedelta(days=expiring_days)):
        return "expiring"
    return "fresh"

def _get_freshness_config(overrides: dict) -> tuple[int, int]:
    raw_ret = overrides.get("evidence_retention_days", 90)
    try:
        retention_days = int(raw_ret)
    except Exception:
        retention_days = 90
    retention_days = max(1, min(3650, retention_days))

    raw_exp = overrides.get("evidence_expiring_days", 14)
    try:
        expiring_days = int(raw_exp)
    except Exception:
        expiring_days = 14
    expiring_days = max(1, min(365, expiring_days))

    return retention_days, expiring_days

def _dt_equal(a: datetime | None, b: datetime | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    a2 = a.astimezone(timezone.utc) if a.tzinfo else a.replace(tzinfo=timezone.utc)
    b2 = b.astimezone(timezone.utc) if b.tzinfo else b.replace(tzinfo=timezone.utc)
    return a2 == b2


def _normalize_source_system(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip().lower()
    if not s:
        return None
    if s not in ALLOWED_SOURCE_SYSTEMS:
        raise ValueError(f"source_system must be one of: {', '.join(sorted(ALLOWED_SOURCE_SYSTEMS))}")
    return s


def _normalize_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise ValueError("tags must be an array of strings")
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        s = t.strip().lower()
        if not s:
            continue
        s = re.sub(r"[^a-z0-9:_\-./]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        if not s:
            continue
        if len(s) > 64:
            s = s[:64]
        out.append(s)
    seen = set()
    uniq = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return uniq[:50]


def get_download_url(storage_key: str) -> dict:
    s3 = s3_client()
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key},
        ExpiresIn=300,
    )
    return {"url": url, "expires_in_seconds": 300}


class EvidenceCreateBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    expires_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    evidence_period_start: Optional[str] = None
    evidence_period_end: Optional[str] = None
    source_system: Optional[str] = None
    source_ref: Optional[str] = Field(default=None, max_length=500)


class EvidencePatchBody(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=120)
    tags: Optional[List[str]] = None

    expires_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    evidence_period_start: Optional[str] = None
    evidence_period_end: Optional[str] = None

    source_system: Optional[str] = None
    source_ref: Optional[str] = Field(default=None, max_length=500)

class EvidenceVerifyBody(BaseModel):
    verified_at: Optional[str] = None
    source_system: Optional[str] = None
    source_ref: Optional[str] = Field(default=None, max_length=500)

class FreshnessScanBody(BaseModel):
    include_deleted: bool = False


@router.post("/freshness/scan")
def enqueue_freshness_scan(body: FreshnessScanBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    with SessionLocal() as session:
        jr = JobRun(
            id=uuid4(),
            tenant_id=ctx.tenant_id,
            job_type="evidence.freshness.scan",
            rq_job_id="temp-" + str(uuid4()),
            status="queued",
            idempotency_key=f"freshness-scan-{ctx.tenant_id}-{int(_now().timestamp())}",
            attempts=0,
            created_at=_now(),
        )
        session.add(jr)
        session.flush()

        q = get_queue()
        rq_job = q.enqueue(
            "app.jobs.evidence_freshness.run_freshness_scan_job",
            job_run_id=str(jr.id),
            tenant_id=str(ctx.tenant_id),
            user_id=str(ctx.user_id),
            include_deleted=bool(body.include_deleted),
        )
        jr.rq_job_id = rq_job.id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.freshness.queued",
            object_type="job_run",
            object_id=str(jr.id),
            meta={"rq_job_id": rq_job.id, "include_deleted": bool(body.include_deleted)},
        )

        session.commit()
        return {"job_run_id": str(jr.id), "rq_job_id": rq_job.id, "status": "queued"}


@router.get("/freshness/scan/{job_run_id}")
def get_freshness_scan(job_run_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    jid = UUID(job_run_id)

    with SessionLocal() as session:
        jr = session.execute(
            select(JobRun).where(JobRun.id == jid, JobRun.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()

        if jr is None:
            raise HTTPException(status_code=404, detail="not found")

        return {
            "id": str(jr.id),
            "job_type": jr.job_type,
            "status": jr.status,
            "attempts": jr.attempts,
            "last_error": jr.last_error,
            "created_at": jr.created_at.isoformat(),
            "started_at": jr.started_at.isoformat() if jr.started_at else None,
            "finished_at": jr.finished_at.isoformat() if jr.finished_at else None,
        }

@router.post("")
def create_evidence(body: EvidenceCreateBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    title = (body.title or "").strip()
    if not title:
        title = (body.original_filename or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")

    description = (body.description or "").strip() or None
    category = (body.category or "").strip() or None

    try:
        tags = _normalize_tags(body.tags)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        expires_at = _parse_dt(body.expires_at, "expires_at")
        last_verified_at = _parse_dt(body.last_verified_at, "last_verified_at")
        eps = _parse_dt(body.evidence_period_start, "evidence_period_start")
        epe = _parse_dt(body.evidence_period_end, "evidence_period_end")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if eps is not None and epe is not None:
        if epe < eps:
            raise HTTPException(status_code=400, detail="evidence_period_end must be >= evidence_period_start")

    try:
        source_system = _normalize_source_system(body.source_system)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    source_ref = (body.source_ref or "").strip() or None
    if source_ref and len(source_ref) > 500:
        raise HTTPException(status_code=400, detail="source_ref too long (max 500)")

    now = _now()

    with SessionLocal() as session:
        item = EvidenceItem(
            tenant_id=ctx.tenant_id,
            title=title,
            description=description,
            category=category,
            tags=tags,
            created_at=now,
            updated_at=now,
            updated_by=ctx.user_id,
            expires_at=expires_at,
            last_verified_at=last_verified_at,
            evidence_period_start=eps,
            evidence_period_end=epe,
            source_system=source_system,
            source_ref=source_ref,
        )
        session.add(item)
        session.flush()

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.create",
            object_type="evidence",
            object_id=str(item.id),
            meta={
                "title": title,
                "category": category,
                "tags": tags,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "evidence_period_start": eps.isoformat() if eps else None,
                "evidence_period_end": epe.isoformat() if epe else None,
                "last_verified_at": last_verified_at.isoformat() if last_verified_at else None,
                "source_system": source_system,
                "source_ref": source_ref,
            },
        )
        session.commit()

        return {"id": str(item.id)}


@router.get("")
def list_evidence(
    limit: int = 50,
    offset: int = 0,
    include_deleted: bool = False,
    ctx: TenantContext = Depends(get_ctx),
) -> list[dict]:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))

    now = _now()

    with SessionLocal() as session:
        overrides = get_overrides(session, ctx.tenant_id)
        retention_days, expiring_days = _get_freshness_config(overrides)

        q = select(EvidenceItem).where(EvidenceItem.tenant_id == ctx.tenant_id)
        if not include_deleted and hasattr(EvidenceItem, "deleted_at"):
            q = q.where(EvidenceItem.deleted_at.is_(None))

        rows = session.execute(
            q.order_by(EvidenceItem.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all()

        out: list[dict] = []
        for r in rows:
            eff_exp = _effective_expires_at(r, retention_days)

            updated_at = getattr(r, "updated_at", None) or r.created_at
            deleted_at = getattr(r, "deleted_at", None)

            expires_at = getattr(r, "expires_at", None)
            last_verified_at = getattr(r, "last_verified_at", None)
            eps = getattr(r, "evidence_period_start", None)
            epe = getattr(r, "evidence_period_end", None)

            out.append(
                {
                    "id": str(r.id),
                    "title": r.title,
                    "description": r.description,
                    "category": getattr(r, "category", None),
                    "tags": list(getattr(r, "tags", []) or []),
                    "created_at": r.created_at.isoformat(),
                    "updated_at": _as_aware_utc(updated_at).isoformat() if updated_at else r.created_at.isoformat(),
                    "deleted_at": _as_aware_utc(deleted_at).isoformat() if deleted_at else None,
                    "storage_key": r.storage_key,
                    "original_filename": r.original_filename,
                    "uploaded_at": _as_aware_utc(r.uploaded_at).isoformat() if r.uploaded_at else None,
                    "content_type": r.content_type,
                    "size_bytes": r.size_bytes,
                    "content_hash": r.content_hash,
                    "expires_at": _as_aware_utc(expires_at).isoformat() if expires_at else None,
                    "effective_expires_at": eff_exp.isoformat() if eff_exp else None,
                    "freshness_status": _freshness_status(eff_exp, now, expiring_days),
                    "age_days": _age_days(r, now),
                    "last_verified_at": _as_aware_utc(last_verified_at).isoformat() if last_verified_at else None,
                    "evidence_period_start": _as_aware_utc(eps).isoformat() if eps else None,
                    "evidence_period_end": _as_aware_utc(epe).isoformat() if epe else None,
                    "source_system": getattr(r, "source_system", None),
                    "source_ref": getattr(r, "source_ref", None),
                }
            )
        return out


@router.get("/{evidence_id}")
def get_evidence(evidence_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)
    now = _now()

    with SessionLocal() as session:
        overrides = get_overrides(session, ctx.tenant_id)
        retention_days, expiring_days = _get_freshness_config(overrides)

        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or item.deleted_at is not None:
            raise HTTPException(status_code=404, detail="not found")

        eff_exp = _effective_expires_at(item, retention_days)

        return {
            "id": str(item.id),
            "title": item.title,
            "description": item.description,
            "category": getattr(item, "category", None),
            "tags": list(getattr(item, "tags", []) or []),
            "created_at": item.created_at.isoformat(),
            "updated_at": _as_aware_utc(item.updated_at).isoformat() if item.updated_at else None,
            "deleted_at": _as_aware_utc(getattr(item, "deleted_at", None)).isoformat() if getattr(item, "deleted_at", None) else None,
            "storage_key": item.storage_key,
            "original_filename": item.original_filename,
            "uploaded_at": _as_aware_utc(item.uploaded_at).isoformat() if item.uploaded_at else None,
            "content_type": item.content_type,
            "size_bytes": item.size_bytes,
            "content_hash": item.content_hash,
            "expires_at": _as_aware_utc(getattr(item, "expires_at", None)).isoformat() if getattr(item, "expires_at", None) else None,
            "effective_expires_at": eff_exp.isoformat() if eff_exp else None,
            "freshness_status": _freshness_status(eff_exp, now, expiring_days),
            "age_days": _age_days(item, now),
            "last_verified_at": _as_aware_utc(getattr(item, "last_verified_at", None)).isoformat() if getattr(item, "last_verified_at", None) else None,
            "evidence_period_start": _as_aware_utc(getattr(item, "evidence_period_start", None)).isoformat() if getattr(item, "evidence_period_start", None) else None,
            "evidence_period_end": _as_aware_utc(getattr(item, "evidence_period_end", None)).isoformat() if getattr(item, "evidence_period_end", None) else None,
            "source_system": getattr(item, "source_system", None),
            "source_ref": getattr(item, "source_ref", None),
        }


@router.patch("/{evidence_id}")
def patch_evidence(evidence_id: str, body: EvidencePatchBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)
    now = _now()

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or getattr(item, "deleted_at", None) is not None:
            raise HTTPException(status_code=404, detail="not found")

        changed: dict[str, Any] = {}

        if body.title is not None:
            t = body.title.strip()
            if not t:
                raise HTTPException(status_code=400, detail="title cannot be empty")
            if t != item.title:
                item.title = t
                changed["title"] = t

        if body.description is not None:
            d = body.description.strip() or None
            if d != item.description:
                item.description = d
                changed["description"] = d

        if body.category is not None:
            c = body.category.strip() or None
            if c != getattr(item, "category", None):
                item.category = c
                changed["category"] = c

        if body.tags is not None:
            try:
                tags = _normalize_tags(body.tags)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if tags != list(getattr(item, "tags", []) or []):
                item.tags = tags
                changed["tags"] = tags

        if body.expires_at is not None:
            try:
                exp = _parse_dt(body.expires_at, "expires_at")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            cur = getattr(item, "expires_at", None)
            if not _dt_equal(cur, exp):
                item.expires_at = exp
                changed["expires_at"] = exp.isoformat() if exp else None

        if body.evidence_period_start is not None:
            try:
                ps = _parse_dt(body.evidence_period_start, "evidence_period_start")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            cur = getattr(item, "evidence_period_start", None)
            if not _dt_equal(cur, ps):
                item.evidence_period_start = ps
                changed["evidence_period_start"] = ps.isoformat() if ps else None

        if body.evidence_period_end is not None:
            try:
                pe = _parse_dt(body.evidence_period_end, "evidence_period_end")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            cur = getattr(item, "evidence_period_end", None)
            if not _dt_equal(cur, pe):
                item.evidence_period_end = pe
                changed["evidence_period_end"] = pe.isoformat() if pe else None

        if ("evidence_period_start" in changed) or ("evidence_period_end" in changed):
            ps2 = getattr(item, "evidence_period_start", None)
            pe2 = getattr(item, "evidence_period_end", None)
            if ps2 is not None and pe2 is not None:
                ps2u = ps2.astimezone(timezone.utc) if ps2.tzinfo else ps2.replace(tzinfo=timezone.utc)
                pe2u = pe2.astimezone(timezone.utc) if pe2.tzinfo else pe2.replace(tzinfo=timezone.utc)
                if pe2u < ps2u:
                    raise HTTPException(status_code=400, detail="evidence_period_end must be >= evidence_period_start")

        if body.last_verified_at is not None:
            try:
                lv = _parse_dt(body.last_verified_at, "last_verified_at")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            cur = getattr(item, "last_verified_at", None)
            if not _dt_equal(cur, lv):
                item.last_verified_at = lv
                changed["last_verified_at"] = lv.isoformat() if lv else None

        if body.source_system is not None:
            try:
                ss = _normalize_source_system(body.source_system)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            cur = getattr(item, "source_system", None)
            if ss != cur:
                item.source_system = ss
                changed["source_system"] = ss

        if body.source_ref is not None:
            sr = body.source_ref.strip() or None
            if sr and len(sr) > 500:
                raise HTTPException(status_code=400, detail="source_ref too long (max 500)")
            cur = getattr(item, "source_ref", None)
            if sr != cur:
                item.source_ref = sr
                changed["source_ref"] = sr

        if not changed:
            return {"ok": True, "changed": False}

        item.updated_at = now
        item.updated_by = ctx.user_id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.update",
            object_type="evidence",
            object_id=str(item.id),
            meta={"changed": changed},
        )
        session.commit()
        return {"ok": True, "changed": True}
@router.post("/{evidence_id}/verify")
def verify_evidence(evidence_id: str, body: EvidenceVerifyBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)
    now = _now()

    try:
        verified_at = _parse_dt(body.verified_at, "verified_at") if body.verified_at is not None else now
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ss: str | None = None
    if body.source_system is not None:
        try:
            ss = _normalize_source_system(body.source_system)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    sr: str | None = None
    if body.source_ref is not None:
        sr = body.source_ref.strip() or None
        if sr and len(sr) > 500:
            raise HTTPException(status_code=400, detail="source_ref too long (max 500)")

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or getattr(item, "deleted_at", None) is not None:
            raise HTTPException(status_code=404, detail="not found")

        item.last_verified_at = verified_at
        if ss is not None:
            item.source_system = ss
        if body.source_ref is not None:
            item.source_ref = sr

        item.updated_at = now
        item.updated_by = ctx.user_id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.verify",
            object_type="evidence",
            object_id=str(item.id),
            meta={
                "verified_at": verified_at.isoformat(),
                "source_system": getattr(item, "source_system", None),
                "source_ref": getattr(item, "source_ref", None),
            },
        )
        session.commit()

    return {"ok": True, "verified_at": verified_at.isoformat()}

@router.delete("/{evidence_id}")
def delete_evidence(evidence_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)
    now = _now()

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None:
            return {"ok": True}

        if item.deleted_at is not None:
            return {"ok": True}

        item.deleted_at = now
        item.deleted_by = ctx.user_id
        item.updated_at = now
        item.updated_by = ctx.user_id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.delete",
            object_type="evidence",
            object_id=str(item.id),
            meta={},
        )
        session.commit()

    return {"ok": True}


@router.post("/{evidence_id}/upload")
async def upload_file(
    evidence_id: str,
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(get_ctx),
    force: bool = Query(False),
) -> dict:
    eid = uuid.UUID(evidence_id)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or item.deleted_at is not None:
            raise HTTPException(status_code=404, detail="not found")

        if item.storage_key is not None and not force:
            write_audit(
                db=session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                action="evidence.upload.rejected",
                object_type="evidence",
                object_id=str(item.id),
                meta={"reason": "already_uploaded"},
            )
            session.commit()
            raise HTTPException(status_code=409, detail="already uploaded (use force=true to overwrite)")

        overwrote = item.storage_key is not None

    sha256 = hashlib.sha256(data).hexdigest()
    storage_key = f"{ctx.tenant_id}/{eid}/{sha256}"

    s3 = s3_client()
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=storage_key,
        Body=data,
        ContentType=file.content_type or "application/octet-stream",
    )

    now = _now()

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or item.deleted_at is not None:
            raise HTTPException(status_code=404, detail="not found")

        item.storage_key = storage_key
        item.original_filename = file.filename
        item.content_type = file.content_type or "application/octet-stream"
        item.content_hash = sha256
        item.size_bytes = len(data)
        item.uploaded_at = now
        item.updated_at = now
        item.updated_by = ctx.user_id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.upload.overwrite" if overwrote else "evidence.upload",
            object_type="evidence",
            object_id=str(item.id),
            meta={"storage_key": storage_key, "sha256": sha256, "size_bytes": len(data)},
        )
        session.commit()

    return {"status": "ok", "storage_key": storage_key, "overwrote": overwrote}


@router.get("/{evidence_id}/download")
def download_file(evidence_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or item.deleted_at is not None or item.storage_key is None:
            raise HTTPException(status_code=404, detail="not found")
        storage_key = item.storage_key
        original_filename = item.original_filename
        content_type = item.content_type

    s3 = s3_client()
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ResponseContentDisposition": f'attachment; filename="{original_filename or (str(eid) + ".bin")}"',
            "ResponseContentType": content_type or "application/octet-stream",
        },
        ExpiresIn=300,
    )
    return {"url": url, "expires_in_seconds": 300}