# apps/api/app/jobs/evidence_freshness.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select

from app.core.audit import write_audit
from app.core.queue import get_queue
from app.db.session import SessionLocal
from app.models.core import JobRun, EvidenceItem
from app.core.tenant_overrides import get_overrides


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _freshness_status(effective_expires_at: datetime | None, now: datetime, expiring_days: int) -> str:
    from datetime import timedelta

    if effective_expires_at is None:
        return "unknown"
    if effective_expires_at <= now:
        return "expired"
    if effective_expires_at <= (now + timedelta(days=expiring_days)):
        return "expiring"
    return "fresh"


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _effective_expires_at(item: EvidenceItem, retention_days: int | None) -> datetime | None:
    from datetime import timedelta

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


def _compute_freshness_counts(session: SessionLocal, tenant_id: str) -> dict[str, Any]:
    """
    Computes counts + sample ids.
    Uses EvidenceItem rows; DOES NOT mutate anything.
    """
    now = _now()
    overrides = get_overrides(session, tenant_id)
    retention_days, expiring_days = _get_freshness_config(overrides)

    q = select(EvidenceItem).where(EvidenceItem.tenant_id == tenant_id)
    if hasattr(EvidenceItem, "deleted_at"):
        q = q.where(EvidenceItem.deleted_at.is_(None))

    items = session.execute(q).scalars().all()

    counts = {"fresh": 0, "expiring": 0, "expired": 0, "unknown": 0}
    sample_ids = {"fresh": [], "expiring": [], "expired": [], "unknown": []}

    for it in items:
        eff = _effective_expires_at(it, retention_days)
        st = _freshness_status(eff, now, expiring_days)
        if st not in counts:
            st = "unknown"
        counts[st] += 1
        if len(sample_ids[st]) < 10:
            sample_ids[st].append(str(it.id))

    return {
        "total": len(items),
        "retention_days": retention_days,
        "expiring_days": expiring_days,
        "freshness_counts": counts,
        "sample_ids": {
            "expired": sample_ids["expired"],
            "expiring": sample_ids["expiring"],
            "unknown": sample_ids["unknown"],
            "fresh": sample_ids["fresh"],
        },
    }


def enqueue_freshness_scan(
    *,
    tenant_id: str,
    actor_user_id: str | None,
    scheduled_local_date: str,
    scheduled_local_hhmm: str,
) -> dict:
    """
    Idempotent-ish enqueue:
    - One scan per tenant per local-date per hhmm.
    """
    idempotency_key = f"freshness-scan:{tenant_id}:{scheduled_local_date}:{scheduled_local_hhmm}"

    with SessionLocal() as session:
        existing = session.execute(
            select(JobRun).where(
                JobRun.tenant_id == tenant_id,
                JobRun.job_type == "evidence.freshness.scan",
                JobRun.idempotency_key == idempotency_key,
                JobRun.status != "failed",
            )
        ).scalar_one_or_none()

        if existing is not None:
            return {"job_run_id": str(existing.id), "status": existing.status, "deduped": True}

        jr = JobRun(
            id=uuid4(),
            tenant_id=tenant_id,
            job_type="evidence.freshness.scan",
            rq_job_id="temp-" + str(uuid4()),
            status="queued",
            idempotency_key=idempotency_key,
            attempts=0,
            created_at=_now(),
        )
        session.add(jr)
        session.flush()

        q = get_queue()
        rq_job = q.enqueue(
            "app.jobs.evidence_freshness.run_freshness_scan_job",
            job_run_id=str(jr.id),
            tenant_id=str(tenant_id),
            actor_user_id=str(actor_user_id) if actor_user_id else None,
        )
        jr.rq_job_id = rq_job.id

        session.commit()
        return {"job_run_id": str(jr.id), "status": "queued", "deduped": False}


def run_freshness_scan_job(job_run_id: str, tenant_id: str, actor_user_id: str | None):
    jid = UUID(job_run_id)

    with SessionLocal() as session:
        jr = session.execute(select(JobRun).where(JobRun.id == jid)).scalar_one()
        jr.status = "running"
        jr.started_at = _now()
        jr.attempts = (jr.attempts or 0) + 1
        jr.last_error = None
        session.commit()

    try:
        with SessionLocal() as session:
            payload = _compute_freshness_counts(session, tenant_id)

            write_audit(
                db=session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="evidence.freshness.scan",
                object_type="tenant",
                object_id=str(tenant_id),
                meta=payload,
            )
            session.commit()

        with SessionLocal() as session:
            jr = session.execute(select(JobRun).where(JobRun.id == jid)).scalar_one()
            jr.status = "finished"
            jr.finished_at = _now()
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
                actor_user_id=actor_user_id,
                action="evidence.freshness.scan.failed",
                object_type="tenant",
                object_id=str(tenant_id),
                meta={"error": str(e)[:2000]},
            )
            session.commit()
        raise