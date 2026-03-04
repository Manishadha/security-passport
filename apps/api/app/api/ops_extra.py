from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException
import sentry_sdk

from app.core.auth import TenantContext, get_ctx

router = APIRouter(prefix="/ops", tags=["ops"])


def require_admin(ctx: TenantContext = Depends(get_ctx)) -> TenantContext:
    if ctx.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return ctx


@router.get("/sentry_test")
def sentry_test(_: TenantContext = Depends(require_admin)) -> dict:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        raise HTTPException(status_code=503, detail="SENTRY_DSN not configured")

    event_id = sentry_sdk.capture_message("sentry_test_event", level="info")
    return {"ok": True, "event_id": event_id}


@router.get("/whoami")
def whoami(ctx: TenantContext = Depends(get_ctx)) -> dict:
    return {
        "tenant_id": str(ctx.tenant_id),
        "user_id": str(ctx.user_id),
        "role": ctx.role,
        "email": ctx.email,
    }