import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal

router = APIRouter(prefix="/audit", tags=["audit"])


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid datetime, expected ISO-8601")


@router.get("/events")
def list_audit_events(
    ctx: TenantContext = Depends(get_ctx),
    limit: int = Query(100, ge=1, le=500),
    cursor: Optional[str] = Query(None),
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
    action: Optional[str] = Query(None),
    object_type: Optional[str] = Query(None),
    actor_user_id: Optional[str] = Query(None),
) -> dict:
    import sqlalchemy as sa

    from_dt = _parse_dt(from_ts)
    to_dt = _parse_dt(to_ts)

    cursor_created_at: Optional[datetime] = None
    cursor_id: Optional[uuid.UUID] = None
    if cursor:
        try:
            c_created_at_s, c_id_s = cursor.split("|", 1)
            cursor_created_at = _parse_dt(c_created_at_s)
            cursor_id = uuid.UUID(c_id_s)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid cursor")

    with SessionLocal() as session:
        md = sa.MetaData()
        bind = session.get_bind()
        e = sa.Table("audit_events", md, autoload_with=bind)

        where = [e.c.tenant_id == ctx.tenant_id]

        if from_dt is not None:
            where.append(e.c.created_at >= from_dt)
        if to_dt is not None:
            where.append(e.c.created_at <= to_dt)
        if action:
            where.append(e.c.action == action)
        if object_type:
            where.append(e.c.object_type == object_type)
        if actor_user_id:
            try:
                where.append(e.c.actor_user_id == uuid.UUID(actor_user_id))
            except Exception:
                raise HTTPException(status_code=400, detail="invalid actor_user_id")

        if cursor_created_at is not None and cursor_id is not None:
            where.append(
                sa.or_(
                    e.c.created_at < cursor_created_at,
                    sa.and_(e.c.created_at == cursor_created_at, e.c.id < cursor_id),
                )
            )

        rows = session.execute(
            sa.select(e)
            .where(sa.and_(*where))
            .order_by(e.c.created_at.desc(), e.c.id.desc())
            .limit(limit + 1)
        ).mappings().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "id": str(r["id"]),
                    "tenant_id": str(r["tenant_id"]),
                    "actor_user_id": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                    "action": r.get("action"),
                    "object_type": r.get("object_type"),
                    "object_id": r.get("object_id"),
                    "metadata": r.get("metadata"),
                    "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                }
            )

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            if last.get("created_at") is not None and last.get("id") is not None:
                dt = last["created_at"]
                dt_s = dt.isoformat().replace("+00:00", "Z") if dt is not None else ""
                next_cursor = f"{dt_s}|{str(last['id'])}"

        return {"items": items, "next_cursor": next_cursor}
