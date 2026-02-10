from datetime import datetime
from rq import get_current_job
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import JobRun


def run() -> None:
    job = get_current_job()
    if job is None:
        return

    with SessionLocal() as session:
        job_run = session.execute(
            select(JobRun).where(JobRun.rq_job_id == job.id)
        ).scalar_one()

        job_run.status = "succeeded"
        job_run.finished_at = datetime.utcnow()
        session.commit()
