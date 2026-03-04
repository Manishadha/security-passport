from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import TenantContext, get_ctx
from app.core.settings import settings

router = APIRouter(prefix="/ops", tags=["ops"])


def require_admin(ctx: TenantContext = Depends(get_ctx)) -> TenantContext:
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return ctx


def _redact_url(url: str | None) -> str | None:
    if not url:
        return None
    return re.sub(r":([^:@/]+)@", r":***@", url)


@router.get("/config")
def ops_config(_: TenantContext = Depends(require_admin)) -> dict:
    db_url = None
    try:
        db_url = settings.database_url
    except Exception:
        db_url = None

    return {
        "env": getattr(settings, "env", None),
        "redis_url": _redact_url(getattr(settings, "redis_url", None)),
        "database_url": _redact_url(db_url),
        "s3_endpoint": getattr(settings, "s3_endpoint", None),
        "s3_bucket": getattr(settings, "s3_bucket", None),
        "jwt_issuer": getattr(settings, "jwt_issuer", None),
        "access_token_minutes": getattr(settings, "jwt_access_token_minutes", None),
    }