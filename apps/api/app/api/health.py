from __future__ import annotations

import os

import redis
from fastapi import APIRouter
from minio import Minio
from sqlalchemy import text

from app.db.session import SessionLocal

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "alive"}


@router.get("/ready")
def ready():
    db_ok = False
    redis_ok = False
    minio_ok = False

    try:
        with SessionLocal() as s:
            s.execute(text("select 1"))
        db_ok = True
    except Exception:
        pass

    try:
        r = redis.from_url(os.environ["REDIS_URL"])
        r.ping()
        redis_ok = True
    except Exception:
        pass

    try:
        client = Minio(
            os.environ.get("MINIO_ENDPOINT") or os.environ["S3_ENDPOINT"].replace("http://","").replace("https://",""),
            access_key=os.environ.get("MINIO_ACCESS_KEY") or os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ.get("MINIO_SECRET_KEY") or os.environ["S3_SECRET_KEY"],
            secure=False,
        )
        client.list_buckets()
        minio_ok = True
    except Exception:
        pass

    if db_ok and redis_ok and minio_ok:
        return {"status": "ready"}

    return {"status": "not_ready", "db": db_ok, "redis": redis_ok, "minio": minio_ok}

@router.get("/env")
def env():
    import os
    return {
        "REDIS_URL": os.getenv("REDIS_URL"),
        "S3_ENDPOINT": os.getenv("S3_ENDPOINT"),
    }

