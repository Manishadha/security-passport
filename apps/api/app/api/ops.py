from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from rq import Queue
from redis.exceptions import RedisError

from app.core.auth import TenantContext, get_ctx
from app.core.queue import get_redis
from app.db.session import SessionLocal
from app.models.core import JobRun

router = APIRouter(prefix="/ops", tags=["ops"])


def _require_admin(ctx: TenantContext) -> None:
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")


@router.get("/queues")
def queues(ctx: TenantContext = Depends(get_ctx)) -> dict:
    _require_admin(ctx)

    try:
        r = get_redis()
        r.ping()
        q = Queue("default", connection=r)

        return {
            "queue": "default",
            "queued": q.count,
            "started": q.started_job_registry.count,
            "failed": q.failed_job_registry.count,
            "deferred": q.deferred_job_registry.count,
            "scheduled": q.scheduled_job_registry.count,
        }
    except RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="queue unavailable")


@router.get("/jobs/recent")
def recent_jobs(
    limit: int = Query(50, ge=1, le=200),
    job_type: str | None = None,
    status: str | None = None,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    _require_admin(ctx)

    with SessionLocal() as session:
        q = select(JobRun).order_by(JobRun.created_at.desc()).limit(limit)
        if job_type:
            q = q.where(JobRun.job_type == job_type)
        if status:
            q = q.where(JobRun.status == status)

        rows = session.execute(q).scalars().all()

        items = []
        for jr in rows:
            items.append(
                {
                    "id": str(jr.id),
                    "tenant_id": str(jr.tenant_id),
                    "job_type": jr.job_type,
                    "status": jr.status,
                    "attempts": jr.attempts,
                    "last_error": jr.last_error,
                    "created_at": jr.created_at.isoformat(),
                    "started_at": jr.started_at.isoformat() if jr.started_at else None,
                    "finished_at": jr.finished_at.isoformat() if jr.finished_at else None,
                }
            )

        return {"items": items}