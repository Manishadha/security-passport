from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal

router = APIRouter(prefix="/activity", tags=["activity"])


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid datetime, expected ISO-8601")


@router.get("/recent")
def recent_activity(
    ctx: TenantContext = Depends(get_ctx),
    limit: int = Query(50, ge=1, le=200),
    since: Optional[str] = Query(None),
) -> dict:
    import sqlalchemy as sa

    since_dt = _parse_dt(since)
    if since_dt is None:
        since_dt = datetime.utcnow() - timedelta(days=7)

    with SessionLocal() as session:
        md = sa.MetaData()
        bind = session.get_bind()
        e = sa.Table("audit_events", md, autoload_with=bind)

        rows = session.execute(
            sa.select(e)
            .where(sa.and_(e.c.tenant_id == ctx.tenant_id, e.c.created_at >= since_dt))
            .order_by(e.c.created_at.desc(), e.c.id.desc())
            .limit(limit)
        ).mappings().all()

        items: list[dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "id": str(r["id"]),
                    "at": r.get("created_at").isoformat() if r.get("created_at") else None,
                    "action": r.get("action"),
                    "actor_user_id": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                    "object_type": r.get("object_type"),
                    "object_id": r.get("object_id"),
                    "metadata": r.get("metadata"),
                }
            )

        return {"since": since_dt.isoformat(), "items": items}
