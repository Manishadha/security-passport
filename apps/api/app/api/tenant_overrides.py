from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.core.tenant_overrides import get_overrides, upsert_overrides
from app.db.session import SessionLocal

router = APIRouter(prefix="/tenants/me", tags=["tenant_overrides"])

class OverridesBody(BaseModel):
    overrides: Dict[str, Any] | None = None

@router.get("/overrides")
def read_overrides(ctx: TenantContext = Depends(get_ctx)) -> dict:
    with SessionLocal() as session:
        data = get_overrides(session, ctx.tenant_id)
        return {"tenant_id": str(ctx.tenant_id), "overrides": data}

@router.put("/overrides")
def replace_overrides(body: OverridesBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    with SessionLocal() as session:
        stored, changed = upsert_overrides(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            new_overrides=body.overrides,
            merge=False,
        )

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="tenant.overrides.replace",
            object_type="tenant",
            object_id=str(ctx.tenant_id),
            meta={"changed": changed},
        )
        session.commit()

        return {"ok": True, "tenant_id": str(ctx.tenant_id), "overrides": stored}

@router.patch("/overrides")
def merge_overrides(body: OverridesBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    with SessionLocal() as session:
        stored, changed = upsert_overrides(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            new_overrides=body.overrides,
            merge=True,
        )

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="tenant.overrides.merge",
            object_type="tenant",
            object_id=str(ctx.tenant_id),
            meta={"changed": changed},
        )
        session.commit()

        return {"ok": True, "tenant_id": str(ctx.tenant_id), "overrides": stored}
