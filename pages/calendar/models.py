"""Event row <-> dict, validation, and DB queries."""
from datetime import datetime

from core.db import execute, query

FIELDS = ("title", "start_at", "end_at", "all_day", "location", "notes")


class ValidationError(ValueError):
    pass


def _parse_iso(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be an ISO-8601 datetime")


def _clean(data: dict, *, partial: bool) -> dict:
    """Validate and normalise incoming event fields. `partial` allows a subset (PATCH)."""
    out = {}
    if "title" in data or not partial:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("title is required")
        out["title"] = title
    if "start_at" in data or not partial:
        out["start_at"] = _parse_iso(data.get("start_at"), "start_at").isoformat()
    if "end_at" in data and data["end_at"] not in (None, ""):
        out["end_at"] = _parse_iso(data["end_at"], "end_at").isoformat()
    elif "end_at" in data:
        out["end_at"] = None
    # end >= start when both are known
    start = out.get("start_at") or (data.get("start_at"))
    if out.get("end_at") and start:
        if _parse_iso(out["end_at"], "end_at") < _parse_iso(start, "start_at"):
            raise ValidationError("end_at must be on or after start_at")
    if "all_day" in data:
        out["all_day"] = 1 if data["all_day"] else 0
    for f in ("location", "notes"):
        if f in data:
            out[f] = data[f] or None
    return out


def to_dict(row) -> dict:
    d = dict(row)
    d["all_day"] = bool(d["all_day"])
    return d


def list_events(start=None, end=None) -> list[dict]:
    sql = "SELECT * FROM events"
    params, where = [], []
    if start:
        where.append("start_at >= ?")
        params.append(start)
    if end:
        where.append("start_at <= ?")
        params.append(end)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY start_at"
    return [to_dict(r) for r in query(sql, params)]


def get_event(event_id: int):
    row = query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    return to_dict(row) if row else None


def create_event(data: dict) -> dict:
    fields = _clean(data, partial=False)
    cols = list(fields)
    cur = execute(
        f"INSERT INTO events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [fields[c] for c in cols],
    )
    return get_event(cur.lastrowid)


def update_event(event_id: int, data: dict):
    if get_event(event_id) is None:
        return None
    fields = _clean(data, partial=True)
    if fields:
        cols = list(fields)
        execute(
            f"UPDATE events SET {','.join(f'{c}=?' for c in cols)} WHERE id = ?",
            [fields[c] for c in cols] + [event_id],
        )
    return get_event(event_id)


def delete_event(event_id: int) -> bool:
    return execute("DELETE FROM events WHERE id = ?", (event_id,)).rowcount > 0
