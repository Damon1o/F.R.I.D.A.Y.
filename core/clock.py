"""Local time. Serverless hosts run in UTC, so never trust the process's local tz.

Zone comes from the `timezone` setting, falling back to FRIDAY_TZ then America/New_York.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FALLBACK_TZ = os.environ.get("FRIDAY_TZ", "America/New_York")


def tz() -> ZoneInfo:
    from core.db import query
    try:
        row = query("SELECT value FROM settings WHERE key = 'timezone'", one=True)
        return ZoneInfo(row["value"]) if row and row["value"] else ZoneInfo(FALLBACK_TZ)
    except Exception:
        return ZoneInfo(FALLBACK_TZ)


def now() -> datetime:
    return datetime.now(tz())


def to_local(dt: datetime) -> datetime:
    """Convert an aware datetime to the configured zone; assume UTC if naive."""
    zone = tz()
    return dt.replace(tzinfo=timezone.utc).astimezone(zone) if dt.tzinfo is None else dt.astimezone(zone)
