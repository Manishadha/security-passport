from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal

router = APIRouter(prefix="/tenant", tags=["tenant"])


DEFAULT_SETTINGS: Dict[str, Any] = {
    "retention": {
        "audit_days": 365,
        "evidence_days": 365,
        "passport_days": 365,
    }
}

ALLOWED_RETENTION_KEYS = {"audit_days", "evidence_days", "passport_days"}


class UpdateSettingsRequest(BaseModel):
    settings: Dict[str, Any]


def _validate_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")

    out: Dict[str, Any] = {}

    if "retention" in payload:
        r = payload["retention"]
        if not isinstance(r, dict):
            raise HTTPException(status_code=400, detail="retention must be an object")

        rr: Dict[str, Any] = {}
        for k, v in r.items():
            if k not in ALLOWED_RETENTION_KEYS:
                raise HTTPException(status_code=400, detail=f"unknown retention key: {k}")
            if not isinstance(v, int):
                raise HTTPException(status_code=400, detail=f"retention.{k} must be an integer")
            if v < 1 or v > 3650:
                raise HTTPException(status_code=400, detail=f"retention.{k} must be between 1 and 3650")
            rr[k] = v

        out["retention"] = rr

    unknown_top = set(payload.keys()) - {"retention"}
    if unknown_top:
        raise HTTPException(status_code=400, detail=f"unknown setting group(s): {sorted(unknown_top)}")

    return out


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@router.get("/settings")
def get_settings(ctx: TenantContext = Depends(get_ctx)) -> dict:
    import sqlalchemy as sa

    with SessionLocal() as session:
        md = sa.MetaData()
        bind = session.get_bind()
        t = sa.Table("tenant_overrides", md, autoload_with=bind)

        row = session.execute(sa.select(t).where(t.c.tenant_id == ctx.tenant_id)).mappings().first()
        overrides = row["settings"] if row and row.get("settings") else {}

        effective = _deep_merge(DEFAULT_SETTINGS, overrides)

        return {
            "tenant_id": str(ctx.tenant_id),
            "defaults": DEFAULT_SETTINGS,
            "overrides": overrides,
            "effective": effective,
        }


@router.put("/settings")
def update_settings(req: UpdateSettingsRequest, ctx: TenantContext = Depends(get_ctx)) -> dict:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    patch = _validate_settings(req.settings or {})

    with SessionLocal() as session:
        md = sa.MetaData()
        bind = session.get_bind()
        t = sa.Table("tenant_overrides", md, autoload_with=bind)

        existing = session.execute(sa.select(t.c.settings).where(t.c.tenant_id == ctx.tenant_id)).mappings().first()
        current = existing["settings"] if existing and existing.get("settings") else {}

        new_settings = _deep_merge(current, patch)
        now = datetime.utcnow()

        stmt = (
            pg_insert(t)
            .values(tenant_id=ctx.tenant_id, settings=new_settings, updated_at=now)
            .on_conflict_do_update(
                index_elements=[t.c.tenant_id],
                set_={"settings": new_settings, "updated_at": now},
            )
        )
        session.execute(stmt)

        try:
            from app.core.audit import write_audit as _write_audit

            _write_audit(
                db=session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                action="tenant.settings.update",
                object_type="tenant",
                object_id=str(ctx.tenant_id),
                meta={"patch": patch},
            )
        except Exception:
            pass

        session.commit()

        effective = _deep_merge(DEFAULT_SETTINGS, new_settings)

        return {
            "ok": True,
            "tenant_id": str(ctx.tenant_id),
            "overrides": new_settings,
            "effective": effective,
        }
