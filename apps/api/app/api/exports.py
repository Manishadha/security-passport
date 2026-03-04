from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from rq import Retry

from app.core.auth import TenantContext, get_ctx
from app.core.queue import get_queue
from app.core.audit import write_audit
from app.core.settings import settings
from app.core.storage import s3_client
from app.db.session import SessionLocal
from app.models.core import JobRun

router = APIRouter(prefix="/exports", tags=["exports"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExportCreateBody(BaseModel):
    template_code: str = Field(min_length=1, max_length=200)
    format: Literal["zip", "docx"] = "zip"


@router.post("")
def create_export(body: ExportCreateBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    template_code = body.template_code.strip()
    if not template_code:
        raise HTTPException(status_code=400, detail="template_code required")

    format = body.format

    bucket = int(_now().timestamp() // 300) * 300
    idempotency_key = f"export-{ctx.tenant_id}-{template_code}-{format}-{bucket}"

    with SessionLocal() as session:
        existing = session.execute(
            select(JobRun).where(
                JobRun.tenant_id == ctx.tenant_id,
                JobRun.job_type == "passport.export",
                JobRun.idempotency_key == idempotency_key,
                JobRun.status != "failed",
            )
        ).scalar_one_or_none()

        if existing is not None:
            return {
                "job_run_id": str(existing.id),
                "rq_job_id": existing.rq_job_id,
                "status": existing.status,
                "deduped": True,
            }

        job_run = JobRun(
            id=uuid4(),
            tenant_id=ctx.tenant_id,
            job_type="passport.export",
            rq_job_id="temp-" + str(uuid4()),
            status="queued",
            idempotency_key=idempotency_key,
            attempts=0,
            created_at=_now(),
        )

        session.add(job_run)
        session.flush()

        q = get_queue()
        rq_job = q.enqueue(
            "app.jobs.exports.run_export_job",
            job_run_id=str(job_run.id),
            tenant_id=str(ctx.tenant_id),
            user_id=str(ctx.user_id),
            template_code=template_code,
            format=format,
            retry=Retry(max=3, interval=[60, 300, 900]),
        )

        job_run.rq_job_id = rq_job.id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="export.queued",
            object_type="export_job",
            object_id=str(job_run.id),
            meta={
                "template_code": template_code,
                "format": format,
                "rq_job_id": rq_job.id,
                "idempotency_key": idempotency_key,
            },
        )

        session.commit()

        return {
            "job_run_id": str(job_run.id),
            "rq_job_id": rq_job.id,
            "status": "queued",
            "deduped": False,
        }


@router.get("/{job_run_id}")
def get_export_status(job_run_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    jid = UUID(job_run_id)

    with SessionLocal() as session:
        jr = session.execute(
            select(JobRun).where(
                JobRun.id == jid,
                JobRun.tenant_id == ctx.tenant_id,
            )
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
            "uploaded_at": jr.uploaded_at.isoformat() if jr.uploaded_at else None,
            "output": {
                "storage_key": jr.output_storage_key,
                "filename": jr.output_filename,
                "content_type": jr.output_content_type,
                "size_bytes": jr.output_size_bytes,
                "sha256": jr.output_sha256,
            },
        }


@router.get("/{job_run_id}/download")
def get_export_download(job_run_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    jid = UUID(job_run_id)

    with SessionLocal() as session:
        jr = session.execute(
            select(JobRun).where(
                JobRun.id == jid,
                JobRun.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()

        if jr is None or jr.status != "finished" or not jr.output_storage_key:
            raise HTTPException(status_code=404, detail="not ready")

        storage_key = jr.output_storage_key
        filename = jr.output_filename
        content_type = jr.output_content_type

    s3 = s3_client()
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
            "ResponseContentType": content_type or "application/octet-stream",
        },
        ExpiresIn=300,
    )

    return {"url": url, "expires_in_seconds": 300}