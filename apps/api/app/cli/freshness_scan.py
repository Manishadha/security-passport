from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.queue import get_queue
from app.core.audit import write_audit
from app.db.session import SessionLocal
from app.models.core import Tenant, JobRun


def _now():
    return datetime.now(timezone.utc)


def _bucket_5min(ts: datetime) -> int:
    return int(ts.timestamp() // 300)


def main() -> int:
    now = _now()
    bucket = _bucket_5min(now)
    q = get_queue()
    enqueued = 0
    reused = 0

    with SessionLocal() as session:
        tenants = session.execute(select(Tenant)).scalars().all()

        for t in tenants:
            idem = f"freshness-scan-{t.id}-{bucket}"

            existing = session.execute(
                select(JobRun).where(
                    JobRun.tenant_id == t.id,
                    JobRun.job_type == "evidence.freshness.scan",
                    JobRun.idempotency_key == idem,
                )
            ).scalar_one_or_none()

            if existing is not None:
                reused += 1
                continue

            jr = JobRun(
                id=uuid4(),
                tenant_id=t.id,
                job_type="evidence.freshness.scan",
                rq_job_id="temp-" + str(uuid4()),
                status="queued",
                idempotency_key=idem,
                attempts=0,
                created_at=now,
            )
            session.add(jr)
            session.flush()

            rq_job = q.enqueue(
                "app.jobs.evidence_freshness.run_freshness_scan_job",
                job_run_id=str(jr.id),
                tenant_id=str(t.id),
                user_id=None,
            )
            jr.rq_job_id = rq_job.id

            write_audit(
                db=session,
                tenant_id=t.id,
                actor_user_id=None,
                action="evidence.freshness.scan.queued",
                object_type="tenant",
                object_id=str(t.id),
                meta={"job_run_id": str(jr.id), "rq_job_id": rq_job.id, "scheduled": True},
            )

            enqueued += 1

        session.commit()

    print(f"freshness_scan scheduled: enqueued={enqueued} reused={reused} tenants={enqueued+reused}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())