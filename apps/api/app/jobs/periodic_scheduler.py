# apps/api/app/jobs/periodic_scheduler.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import Tenant
from app.core.tenant_overrides import get_overrides
from app.jobs.evidence_freshness import enqueue_freshness_scan


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TenantSchedule:
    enabled: bool
    tz: str
    hour: int
    minute: int


def _parse_schedule(overrides: dict) -> TenantSchedule:
    enabled = overrides.get("freshness_scan_enabled", True) is True

    tz = (overrides.get("freshness_scan_timezone") or "UTC").strip() or "UTC"
    try:
        ZoneInfo(tz)
    except Exception:
        tz = "UTC"

    raw_h = overrides.get("freshness_scan_hour", 8)
    raw_m = overrides.get("freshness_scan_minute", 0)

    try:
        hour = int(raw_h)
    except Exception:
        hour = 8
    try:
        minute = int(raw_m)
    except Exception:
        minute = 0

    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))

    return TenantSchedule(enabled=enabled, tz=tz, hour=hour, minute=minute)


def _due_within_window(local_now: datetime, sched: TenantSchedule, window_minutes: int) -> bool:
    # Scheduled local time for "today"
    scheduled = local_now.replace(
        hour=sched.hour, minute=sched.minute, second=0, microsecond=0
    )

    # Enqueue if local_now is in [scheduled, scheduled + window)
    return scheduled <= local_now < (scheduled + timedelta(minutes=window_minutes))


def run_periodic_scheduler(*, actor_user_id: str | None = None, window_minutes: int = 5) -> dict:
    """
    Intended to be called every ~5 minutes.
    `window_minutes` should match  scheduler cadence.
    """
    now_utc = _now()
    enqueued = 0
    skipped = 0
    deduped = 0

    skip_reasons: dict[str, int] = {}
    sample: list[dict] = []

    def _bump(reason: str):
        nonlocal skipped
        skipped += 1
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    with SessionLocal() as session:
        tenants = session.execute(select(Tenant)).scalars().all()

        for t in tenants:
            overrides = get_overrides(session, str(t.id))
            sched = _parse_schedule(overrides)

            if not sched.enabled:
                _bump("disabled")
                continue

            try:
                tzinfo = ZoneInfo(sched.tz)
            except Exception:
                tzinfo = ZoneInfo("UTC")

            local_now = now_utc.astimezone(tzinfo)

            if not _due_within_window(local_now, sched, window_minutes):
                _bump("not_due")
                if len(sample) < 10:
                    sample.append(
                        {
                            "tenant_id": str(t.id),
                            "reason": "not_due",
                            "tz": sched.tz,
                            "scheduled_hhmm": f"{sched.hour:02d}:{sched.minute:02d}",
                            "local_now_hhmm": f"{local_now.hour:02d}:{local_now.minute:02d}",
                        }
                    )
                continue

            local_date = local_now.date().isoformat()
            hhmm = f"{sched.hour:02d}{sched.minute:02d}"

            res = enqueue_freshness_scan(
                tenant_id=str(t.id),
                actor_user_id=actor_user_id,
                scheduled_local_date=local_date,
                scheduled_local_hhmm=hhmm,
            )
            if res.get("deduped"):
                deduped += 1
            else:
                enqueued += 1

    return {
        "ok": True,
        "now_utc": now_utc.isoformat(),
        "window_minutes": window_minutes,
        "enqueued": enqueued,
        "deduped": deduped,
        "skipped": skipped,
        "skip_reasons": skip_reasons,
        "sample": sample,
    }