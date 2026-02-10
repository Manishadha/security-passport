import uuid
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text, select

from app.api.schemas import RegisterRequest, LoginRequest, TokenResponse, MeResponse
from app.core.auth import TenantContext, get_ctx
from app.core.security import hash_password, verify_password, create_access_token
from app.core.settings import settings
from app.core.audit import write_audit
from app.db.session import SessionLocal
from app.models.core import Tenant, User, Membership
from app.api.evidence import router as evidence_router
from app.core.queue import get_redis

app = FastAPI(title="securitypassport")

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
    return MeResponse(
        user_id=str(ctx.user_id),
        tenant_id=str(ctx.tenant_id),
        role=ctx.role,
        email=ctx.email,
    )


app.include_router(evidence_router)
