from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.queue import get_queue
from app.core.audit import write_audit
from app.db.session import SessionLocal
from app.models.core import JobRun, AuditEvent


router = APIRouter(prefix="/evidence/freshness", tags=["evidence-freshness"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bucket_5min(ts: datetime) -> int:
    return int(ts.timestamp() // 300)


@router.post("/scan")
def create_freshness_scan(ctx: TenantContext = Depends(get_ctx)) -> dict:
    now = _now()
    bucket = _bucket_5min(now)
    idem = f"freshness-scan-{ctx.tenant_id}-{bucket}"

    with SessionLocal() as session:
        # idempotent-ish: reuse queued/running/finished within same 5-min bucket
        existing = session.execute(
            select(JobRun).where(
                JobRun.tenant_id == ctx.tenant_id,
                JobRun.job_type == "evidence.freshness.scan",
                JobRun.idempotency_key == idem,
            )
        ).scalar_one_or_none()

        if existing is not None:
            return {"job_run_id": str(existing.id), "status": existing.status, "idempotent": True}

        job_run = JobRun(
            id=uuid4(),
            tenant_id=ctx.tenant_id,
            job_type="evidence.freshness.scan",
            rq_job_id="temp-" + str(uuid4()),
            status="queued",
            idempotency_key=idem,
            attempts=0,
            created_at=now,
        )
        session.add(job_run)
        session.flush()

        q = get_queue()
        rq_job = q.enqueue(
            "app.jobs.evidence_freshness.run_freshness_scan_job",
            job_run_id=str(job_run.id),
            tenant_id=str(ctx.tenant_id),
            user_id=str(ctx.user_id),
        )
        job_run.rq_job_id = rq_job.id

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.freshness.scan.queued",
            object_type="tenant",
            object_id=str(ctx.tenant_id),
            meta={"job_run_id": str(job_run.id), "rq_job_id": rq_job.id},
        )

        session.commit()

    return {"job_run_id": str(job_run.id), "status": "queued", "idempotent": False}


@router.get("/scan/{job_run_id}")
def get_freshness_scan(job_run_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    jid = UUID(job_run_id)
    with SessionLocal() as session:
        jr = session.execute(
            select(JobRun).where(
                JobRun.id == jid,
                JobRun.tenant_id == ctx.tenant_id,
                JobRun.job_type == "evidence.freshness.scan",
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
        }


@router.get("/latest")
def latest_freshness_summary(ctx: TenantContext = Depends(get_ctx)) -> dict:
    with SessionLocal() as session:
        ev = session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == ctx.tenant_id,
                AuditEvent.action == "evidence.freshness.scan",
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if ev is None:
            return {"found": False}

        return {
            "found": True,
            "created_at": ev.created_at.isoformat(),
            "meta": ev.meta,  # NOTE: model maps JSONB column "metadata" to attr "meta"
        }