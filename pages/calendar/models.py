"""Event row <-> dict, validation, and DB queries."""
from datetime import datetime

from dateutil.parser import isoparse
from dateutil.rrule import rrulestr
from flask import g

from core import undo
from core.db import execute, query

FIELDS = ("title", "start_at", "end_at", "all_day", "location", "notes", "rrule")


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
    if "rrule" in data:
        rr = (data["rrule"] or "").strip()
        if rr:
            start_str = out.get("start_at") or data.get("start_at") or data.get("_existing_start_at")
            dtstart = isoparse(start_str) if start_str else None
            try:
                rrulestr(rr, dtstart=dtstart)
            except (ValueError, TypeError):
                raise ValidationError("rrule must be a valid RFC-5545 RRULE")
            out["rrule"] = rr
        else:
            out["rrule"] = None
    for f in ("location", "notes"):
        if f in data:
            out[f] = data[f] or None
    return out


def to_dict(row) -> dict:
    d = dict(row)
    d["all_day"] = bool(d["all_day"])
    return d


def _raw(event_id: int):
    return query("SELECT * FROM events WHERE id = %s", (event_id,), one=True)


def _naive(value):
    """Parse an ISO string to a tz-naive datetime (the app stores local wall time)."""
    dt = isoparse(value) if isinstance(value, str) else value
    return dt.replace(tzinfo=None)


def _expand(master: dict, start: str, end: str) -> list[dict]:
    """Yield occurrence dicts for a recurring master within [start, end]."""
    dtstart = _naive(master["start_at"])
    rule = rrulestr(master["rrule"], dtstart=dtstart)
    win_start, win_end = _naive(start), _naive(end)
    skip = set((master.get("exdates") or "").split(",")) if master.get("exdates") else set()
    duration = (_naive(master["end_at"]) - dtstart) if master.get("end_at") else None
    out = []
    for occ in rule.between(win_start, win_end, inc=True):
        iso = occ.isoformat()
        if iso in skip:
            continue
        d = to_dict(master)
        d["start_at"] = iso
        if duration is not None:
            d["end_at"] = (occ + duration).isoformat()
        d["occurrence_of"] = master["id"]
        out.append(d)
    return out


def list_events(start=None, end=None) -> list[dict]:
    # Non-recurring rows: window-filtered as before.
    sql, params, where = "SELECT * FROM events WHERE rrule IS NULL", [], []
    if start:
        where.append("start_at >= %s")
        params.append(start)
    if end:
        where.append("start_at <= %s")
        params.append(end)
    if where:
        sql += " AND " + " AND ".join(where)
    rows = [to_dict(r) for r in query(sql, params)]

    # Recurring masters: expand within the window if one is given, else return as-is.
    masters = [dict(r) for r in query("SELECT * FROM events WHERE rrule IS NOT NULL")]
    for m in masters:
        rows.extend(_expand(m, start, end) if (start and end) else [to_dict(m)])

    return sorted(rows, key=lambda e: e["start_at"])


def get_event(event_id: int):
    row = _raw(event_id)
    return to_dict(row) if row else None


def create_event(data: dict) -> dict:
    fields = _clean(data, partial=False)
    cols = list(fields)
    row = execute(
        f"INSERT INTO events ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
        [fields[c] for c in cols],
    ).fetchone()
    undo.record("delete", "events", row["id"], session_id=getattr(g, "session_id", "default"))
    return get_event(row["id"])


def update_event(event_id: int, data: dict):
    prior = _raw(event_id)
    if prior is None:
        return None
    fields = _clean(data, partial=True)
    if fields:
        cols = list(fields)
        undo.record("update", "events", event_id, {c: dict(prior)[c] for c in cols}, session_id=getattr(g, "session_id", "default"))
        execute(
            f"UPDATE events SET {','.join(f'{c}=%s' for c in cols)} WHERE id = %s",
            [fields[c] for c in cols] + [event_id],
        )
    return get_event(event_id)


def skip_occurrence(event_id: int, occ_iso: str) -> bool:
    """Spec L — hide a single occurrence of a recurring event by adding it to EXDATE."""
    row = _raw(event_id)
    if row is None or not row["rrule"]:
        return False
    occ = isoparse(occ_iso).isoformat()
    exdates = [d for d in (row["exdates"] or "").split(",") if d]
    if occ not in exdates:
        exdates.append(occ)
        undo.record("update", "events", event_id, {"exdates": row["exdates"]}, session_id=getattr(g, "session_id", "default"))
        execute("UPDATE events SET exdates = %s WHERE id = %s", (",".join(exdates), event_id))
    return True


def delete_event(event_id: int) -> bool:
    row = _raw(event_id)
    if row is None:
        return False
    undo.record("restore", "events", None, dict(row), session_id=getattr(g, "session_id", "default"))
    return execute("DELETE FROM events WHERE id = %s", (event_id,)).rowcount > 0
