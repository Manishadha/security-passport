from __future__ import annotations

import os
from datetime import datetime

import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.api.activity import router as activity_router
from app.api.audit import router as audit_router
from app.api.evidence import router as evidence_router
from app.api.evidence_freshness import router as evidence_freshness_router
from app.api.exports import router as exports_router
from app.api.freshness import router as freshness_router
from app.api.health import router as health_router
from app.api.ops import router as ops_router
from app.api.ops_config import router as ops_config_router
from app.api.ops_extra import router as ops_extra_router
from app.api.passport import router as passport_router
from app.api.questionnaires import router as questionnaires_router
from app.api.schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.api.share_links import public_router as share_public_router
from app.api.share_links import router as share_links_router
from app.api.tenant_overrides import router as tenant_overrides_router
from app.api.tenant_settings import router as tenant_settings_router
from app.api.version import router as version_router
from app.core.audit import write_audit
from app.core.auth import TenantContext, get_ctx
from app.core.log_context import request_id_var
from app.core.logging import configure_logging
from app.core.queue import get_redis
from app.core.rate_limit import RateLimitMiddleware, default_rate_limit_rules
from app.core.sentry_context import SentryContextMiddleware
from app.core.security import create_access_token, hash_password, verify_password
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.settings import settings
from app.core.http_middleware import RequestLoggingMiddleware
from app.db.session import SessionLocal
from app.models.core import Membership, Tenant, User

configure_logging()

dsn = os.getenv("SENTRY_DSN")
if dsn:
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)

app = FastAPI(title="securitypassport")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:58000",
        "http://127.0.0.1:58000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = request.headers.get("x-request-id") or request_id_var.get()
    headers = {"X-Request-Id": rid} if rid else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": rid}, headers=headers)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = request.headers.get("x-request-id") or request_id_var.get()
    headers = {"X-Request-Id": rid} if rid else None
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "request_id": rid},
        headers=headers,
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = request.headers.get("x-request-id") or request_id_var.get()
    headers = {"X-Request-Id": rid} if rid else None
    return JSONResponse(status_code=500, content={"detail": "internal server error", "request_id": rid}, headers=headers)

@app.get("/health/redis")
def health_redis() -> dict:
    r = get_redis()
    r.ping()
    return {"status": "ok"}

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/health/db")
def health_db() -> dict:
    with SessionLocal() as session:
        session.execute(text("select 1"))
    return {"status": "ok"}

@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest) -> TokenResponse:
    with SessionLocal() as session:
        existing = session.execute(select(User).where(User.email == str(req.email))).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="email already registered")

        tenant = Tenant(name=req.tenant_name, created_at=datetime.utcnow())
        user = User(email=str(req.email), password_hash=hash_password(req.password), created_at=datetime.utcnow())
        session.add_all([tenant, user])
        session.flush()

        membership = Membership(tenant_id=tenant.id, user_id=user.id, role="admin", created_at=datetime.utcnow())
        session.add(membership)

        write_audit(
            db=session,
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="auth.register",
            object_type="user",
            object_id=str(user.id),
            meta={"email": str(req.email)},
        )
        session.commit()

        token = create_access_token(
            secret_key=settings.jwt_secret_key,
            issuer=settings.jwt_issuer,
            subject=str(user.id),
            expires_minutes=settings.jwt_access_token_minutes,
            claims={"tenant_id": str(tenant.id)},
        )
        return TokenResponse(access_token=token)

@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    with SessionLocal() as session:
        user = session.execute(select(User).where(User.email == str(req.email))).scalar_one_or_none()
        if user is None or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid credentials")

        membership = session.execute(select(Membership).where(Membership.user_id == user.id)).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=403, detail="no tenant membership")

        write_audit(
            db=session,
            tenant_id=membership.tenant_id,
            actor_user_id=user.id,
            action="auth.login",
            object_type="user",
            object_id=str(user.id),
            meta={},
        )
        session.commit()

        token = create_access_token(
            secret_key=settings.jwt_secret_key,
            issuer=settings.jwt_issuer,
            subject=str(user.id),
            expires_minutes=settings.jwt_access_token_minutes,
            claims={"tenant_id": str(membership.tenant_id)},
        )
        return TokenResponse(access_token=token)

@app.get("/me", response_model=MeResponse)
def me(ctx: TenantContext = Depends(get_ctx)) -> MeResponse:
    return MeResponse(user_id=str(ctx.user_id), tenant_id=str(ctx.tenant_id), role=ctx.role, email=ctx.email)

app.include_router(evidence_router)
app.include_router(passport_router)
app.include_router(questionnaires_router)
app.include_router(health_router)
app.include_router(audit_router)
app.include_router(activity_router)
app.include_router(tenant_settings_router)
app.include_router(tenant_overrides_router)
app.include_router(share_links_router)
app.include_router(share_public_router)
app.include_router(exports_router)
app.include_router(evidence_freshness_router)
app.include_router(freshness_router)
app.include_router(ops_router)
app.include_router(version_router)
app.include_router(ops_config_router)
app.include_router(ops_extra_router)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, rules=default_rate_limit_rules())
app.add_middleware(SentryContextMiddleware)