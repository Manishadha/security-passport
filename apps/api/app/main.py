from fastapi import FastAPI
from sqlalchemy import text
from app.db.session import SessionLocal

app = FastAPI(title="securitypassport")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/health/db")
def health_db() -> dict:
    with SessionLocal() as session:
        session.execute(text("select 1"))
    return {"status": "ok"}
