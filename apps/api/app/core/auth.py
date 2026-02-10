import uuid
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.core import Membership, User

bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    email: str

def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        pass

def get_ctx(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> TenantContext:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing token")

    token = creds.credentials
    try:
        payload = decode_access_token(token=token, secret_key=settings.jwt_secret_key, issuer=settings.jwt_issuer)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")

    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not sub or not tenant_id:
        raise HTTPException(status_code=401, detail="invalid token")

    user_id = uuid.UUID(str(sub))
    tenant_uuid = uuid.UUID(str(tenant_id))

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")

    membership = db.execute(
        select(Membership).where(Membership.user_id == user_id, Membership.tenant_id == tenant_uuid)
    ).scalar_one_or_none()

    if membership is None:
        raise HTTPException(status_code=403, detail="not a member")

    return TenantContext(tenant_id=tenant_uuid, user_id=user_id, role=membership.role, email=user.email)
