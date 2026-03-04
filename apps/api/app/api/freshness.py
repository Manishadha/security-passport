# apps/api/app/api/freshness.py
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.tenant_overrides import get_overrides
from app.db.session import SessionLocal
from app.jobs.evidence_freshness import enqueue_freshness_scan
from app.models.core import AuditEvent, JobRun

router = APIRouter(prefix="/evidence/freshness", tags=["evidence-freshness"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/scan")
def scan_now(ctx: TenantContext = Depends(get_ctx)) -> dict:
    """
    Enqueue a freshness scan immediately.
    Uses tenant schedule timezone (or UTC) to compute idempotency key.
    """
    with SessionLocal() as session:
        overrides = get_overrides(session, ctx.tenant_id)

    tz = (overrides.get("freshness_scan_timezone") or "UTC").strip() or "UTC"
    try:
        z = ZoneInfo(tz)
    except Exception:
        z = ZoneInfo("UTC")

    local_now = _now().astimezone(z)
    local_date = local_now.date().isoformat()
    hhmm = f"{local_now.hour:02d}{local_now.minute:02d}"

    return enqueue_freshness_scan(
        tenant_id=str(ctx.tenant_id),
        actor_user_id=str(ctx.user_id),
        scheduled_local_date=local_date,
        scheduled_local_hhmm=hhmm,
    )


@router.get("/job/{job_run_id}")
def get_job(job_run_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
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


@router.get("/latest")
def latest(ctx: TenantContext = Depends(get_ctx)) -> dict:
    """
    Returns latest scan summary from audit events.
    """
    with SessionLocal() as session:
        ev = session.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == ctx.tenant_id, AuditEvent.action == "evidence.freshness.scan")
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if ev is None:
            return {"ok": True, "has_scan": False}

        return {
            "ok": True,
            "has_scan": True,
            "created_at": ev.created_at.isoformat(),
            "summary": ev.meta,
        }