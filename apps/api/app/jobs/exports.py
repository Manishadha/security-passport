import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.audit import write_audit
from app.core.settings import settings
from app.core.storage import s3_client
from app.core.tenant_overrides import get_overrides
from app.db.session import SessionLocal
from app.models.core import JobRun
from app.services.passport_zip import build_passport_zip_bytes
from app.api.passport import _build_pack_via_db, _apply_passport_overrides, _render_docx_bytes
from app.core.auth import TenantContext


def _now():
    return datetime.now(timezone.utc)


def _build_export_zip(session, tenant_id: str, template_code: str) -> tuple[bytes, str, dict]:
    ctx = TenantContext(tenant_id=tenant_id, user_id=None, role="system", email="system@local")  # adjust if your TenantContext requires these
    overrides = get_overrides(session, tenant_id)

    pack = _build_pack_via_db(session=session, ctx=ctx, template_code=template_code)
    pack = _apply_passport_overrides(pack, overrides, "passport_zip_include_evidence")
    docx_bytes = _render_docx_bytes(pack)

    include_evidence = overrides.get("passport_zip_include_evidence", True) is True

    out_bytes, evr = build_passport_zip_bytes(
        template_code=template_code,
        tenant_id=str(tenant_id),
        pack=pack,
        docx_bytes=docx_bytes,
        include_evidence=include_evidence,
    )

    sha = hashlib.sha256(out_bytes).hexdigest()

    meta = {
        "format": "zip",
        "evidence_total": evr.evidence_total,
        "evidence_downloaded": evr.evidence_downloaded,
        "evidence_failed": evr.evidence_failed,
        "freshness_counts": evr.freshness_counts,
    }

    return out_bytes, sha, meta


def run_export_job(job_run_id: str, tenant_id: str, user_id: str | None, template_code: str, format: str):
    jid = UUID(job_run_id)

    with SessionLocal() as session:
        jr = session.execute(select(JobRun).where(JobRun.id == jid)).scalar_one()
        jr.status = "running"
        jr.started_at = _now()
        jr.attempts = (jr.attempts or 0) + 1
        jr.last_error = None
        session.commit()

    try:
        if format not in ("zip",):
            raise ValueError("unsupported format")

        with SessionLocal() as session:
            out_bytes, sha256, passport_meta = _build_export_zip(
                session=session, tenant_id=tenant_id, template_code=template_code
            )

        filename = f"{template_code}.zip"
        content_type = "application/zip"
        storage_key = f"exports/{tenant_id}/{job_run_id}/{filename}"

        s3 = s3_client()
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=storage_key,
            Body=out_bytes,
            ContentType=content_type,
        )

        with SessionLocal() as session:
            jr = session.execute(select(JobRun).where(JobRun.id == jid)).scalar_one()
            jr.status = "finished"
            jr.finished_at = _now()
            jr.output_storage_key = storage_key
            jr.output_filename = filename
            jr.output_content_type = content_type
            jr.output_size_bytes = len(out_bytes)
            jr.output_sha256 = sha256
            session.commit()

            write_audit(
                db=session,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                action="export.completed",
                object_type="export_job",
                object_id=str(job_run_id),
                meta={
                    "template_code": template_code,
                    "format": format,
                    "storage_key": storage_key,
                    "sha256": sha256,
                    "size_bytes": len(out_bytes),
                    **passport_meta,
                },
            )
            session.commit()

    except Exception as e:
        with SessionLocal() as session:
            jr = session.execute(select(JobRun).where(JobRun.id == jid)).scalar_one()
            jr.status = "failed"
            jr.last_error = str(e)[:1000]
            jr.finished_at = _now()
            session.commit()

            write_audit(
                db=session,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                action="export.failed",
                object_type="export_job",
                object_id=str(job_run_id),
                meta={"error": str(e)[:2000], "error_type": type(e).__name__},
            )
            session.commit()
        raise