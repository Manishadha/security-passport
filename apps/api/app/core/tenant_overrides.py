import uuid
from datetime import datetime
from typing import Any, Dict, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

ALLOWED_OVERRIDE_KEYS = {
    "ui_theme",
    "passport_zip_include_evidence",
    "passport_docx_include_evidence",
    "evidence_retention_days",
    "evidence_expiring_days",
    "freshness_scan_enabled",
    "freshness_scan_timezone",
    "freshness_scan_hour",
    "freshness_scan_minute",
}

RESERVED_KEYS = {
    "jwt_secret_key",
    "postgres_password",
    "postgres_user",
    "postgres_host",
    "postgres_db",
    "s3_secret_key",
    "s3_access_key",
    "redis_url",
}

def validate_overrides(input_settings: Dict[str, Any] | None) -> Dict[str, Any]:
    if input_settings is None:
        return {}
    if not isinstance(input_settings, dict):
        raise ValueError("overrides must be object")

    cleaned: Dict[str, Any] = {}

    for key, value in input_settings.items():
        if key in RESERVED_KEYS:
            continue
        if key not in ALLOWED_OVERRIDE_KEYS:
            continue

        if key == "ui_theme":
            if value in ("dark", "light"):
                cleaned[key] = value
            continue

        if key in ("passport_zip_include_evidence", "passport_docx_include_evidence", "freshness_scan_enabled"):
            if isinstance(value, bool):
                cleaned[key] = value
            continue

        if key == "evidence_retention_days":
            if isinstance(value, int) and 1 <= value <= 3650:
                cleaned[key] = value
            continue

        if key == "evidence_expiring_days":
            if isinstance(value, int) and 1 <= value <= 365:
                cleaned[key] = value
            continue

        if key == "freshness_scan_timezone":
            if isinstance(value, str):
                tz = value.strip()
                if tz:
                    try:
                        ZoneInfo(tz)
                        cleaned[key] = tz
                    except Exception:
                        pass
            continue

        if key == "freshness_scan_hour":
            if isinstance(value, int) and 0 <= value <= 23:
                cleaned[key] = value
            continue

        if key == "freshness_scan_minute":
            if isinstance(value, int) and 0 <= value <= 59:
                cleaned[key] = value
            continue

    return cleaned

def _table(db: Session):
    md = sa.MetaData()
    bind = db.get_bind()
    return sa.Table("tenant_overrides", md, autoload_with=bind)

def get_overrides(db: Session, tenant_id: uuid.UUID) -> Dict[str, Any]:
    t = _table(db)
    row = db.execute(sa.select(t.c.settings).where(t.c.tenant_id == tenant_id)).first()
    if not row:
        return {}
    return dict(row[0] or {})

def upsert_overrides(
    db: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    new_overrides: Dict[str, Any] | None,
    merge: bool,
) -> Tuple[Dict[str, Any], bool]:
    safe_settings = validate_overrides(new_overrides)

    t = _table(db)
    existing = get_overrides(db, tenant_id)

    merged = {**existing, **safe_settings} if merge else dict(safe_settings)
    changed = merged != existing

    now = datetime.utcnow()

    values: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "settings": merged,
        "created_at": now,
        "updated_at": now,
    }

    if "id" in t.c:
        values["id"] = uuid.uuid4()

    stmt = (
        pg_insert(t)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["tenant_id"],
            set_={"settings": merged, "updated_at": now},
        )
        .returning(t.c.settings)
    )

    row = db.execute(stmt).first()
    stored = dict(row[0] if row else merged)

    return stored, changed