import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.core import AuditEvent

def write_audit(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: str,
    meta: dict,
) -> None:
    ev = AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        meta=meta,
        created_at=datetime.utcnow(),
    )
    db.add(ev)
