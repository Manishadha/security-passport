from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(*, secret_key: str, issuer: str, subject: str, expires_minutes: int, claims: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        **claims,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")

def decode_access_token(*, token: str, secret_key: str, issuer: str) -> dict[str, Any]:
    return jwt.decode(token, secret_key, algorithms=["HS256"], issuer=issuer)
