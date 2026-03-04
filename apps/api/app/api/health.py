from __future__ import annotations

import redis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.settings import settings
from app.core.storage import s3_client
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

    # --- DB ---
    try:
        with SessionLocal() as s:
            s.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False

    
    try:
        r = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        redis_ok = (r.ping() is True)
    except Exception:
        redis_ok = False

    
    try:
        s3 = s3_client()
        s3.list_buckets()
        minio_ok = True
    except Exception:
        minio_ok = False

    status = "ready" if (db_ok and redis_ok and minio_ok) else "not_ready"
    return {"status": status, "db": db_ok, "redis": redis_ok, "minio": minio_ok}


@router.get("/env")
def env():
    
    import os

    return {
        "env": {
            "REDIS_URL": os.getenv("REDIS_URL"),
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT"),
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT"),
        },
        "settings": {
            "redis_url": getattr(settings, "redis_url", None),
            "s3_bucket": getattr(settings, "s3_bucket", None),
            "s3_endpoint": getattr(settings, "s3_endpoint", None),
            "s3_endpoint_url": getattr(settings, "s3_endpoint_url", None),
        },
    }