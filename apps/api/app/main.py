import uuid
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy import text

from app.core.queue import get_queue
from app.db.session import SessionLocal
from app.models.core import JobRun

app = FastAPI(title="securitypassport")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/health/db")
def health_db() -> dict:
    with SessionLocal() as session:
        session.execute(text("select 1"))
    return {"status": "ok"}

@app.post("/jobs/ping")
def enqueue_ping() -> dict:
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    idempotency_key = "ping:v1"

    rq_job_id = str(uuid.uuid4())

    with SessionLocal() as session:
        jr = JobRun(
            tenant_id=tenant_id,
            job_type="ping",
            rq_job_id=rq_job_id,
            status="queued",
            idempotency_key=idempotency_key,
            attempts=0,
            created_at=datetime.utcnow(),
        )
        session.add(jr)
        session.commit()

    q = get_queue()
    q.enqueue("app.jobs.ping.run", job_id=rq_job_id)

    return {"rq_job_id": rq_job_id}
