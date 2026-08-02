"""Todo row <-> dict, validation, and DB queries."""
from datetime import datetime, timezone
from flask import g

from core import undo
from core.db import execute, query
from pages.calendar.models import ValidationError, _parse_iso


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    return d


def _raw(todo_id: int):
    return query("SELECT * FROM todos WHERE id = %s", (todo_id,), one=True)


def list_todos(done=None, tag=None) -> list[dict]:
    sql = "SELECT * FROM todos"
    params, where = [], []
    if done is not None:
        where.append("done = %s")
        params.append(1 if done else 0)
    if tag:
        where.append("tag = %s")
        params.append(tag)
    if where:
        sql += " WHERE " + " AND ".join(where)
    # open first, then manual order (0 = never dragged), then by due date
    # (nulls last), newest created last
    sql += " ORDER BY done, position, due_at IS NULL, due_at, created_at"
    return [to_dict(r) for r in query(sql, params)]


def reorder(ids: list[int]) -> None:
    """Write the given ids as positions 1..n. Ids not listed keep position 0."""
    for i, todo_id in enumerate(ids, start=1):
        execute("UPDATE todos SET position = %s WHERE id = %s", (i, int(todo_id)))


def list_tags() -> list[str]:
    rows = query("SELECT DISTINCT tag FROM todos WHERE tag IS NOT NULL ORDER BY tag")
    return [r["tag"] for r in rows]


def get_todo(todo_id: int):
    row = _raw(todo_id)
    return to_dict(row) if row else None


def create_todo(data: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValidationError("title is required")
    due_at = data.get("due_at")
    if due_at:
        due_at = _parse_iso(due_at, "due_at").isoformat()
    row = execute(
        "INSERT INTO todos (title, due_at, notes, tag) VALUES (%s, %s, %s, %s) RETURNING id",
        (title, due_at or None, data.get("notes") or None, data.get("tag") or None),
    ).fetchone()
    undo.record("delete", "todos", row["id"], session_id=getattr(g, "session_id", "default"))
    return get_todo(row["id"])


def update_todo(todo_id: int, data: dict):
    current = get_todo(todo_id)
    if current is None:
        return None
    prior = dict(_raw(todo_id))
    sets, params, changed = [], [], []
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("title is required")
        sets.append("title = %s")
        params.append(title)
        changed.append("title")
    if "due_at" in data:
        due = data["due_at"]
        due = _parse_iso(due, "due_at").isoformat() if due else None
        sets.append("due_at = %s")
        params.append(due)
        changed.append("due_at")
    if "notes" in data:
        sets.append("notes = %s")
        params.append(data["notes"] or None)
        changed.append("notes")
    if "tag" in data:
        sets.append("tag = %s")
        params.append(data["tag"] or None)
        changed.append("tag")
    if "done" in data:
        done = 1 if data["done"] else 0
        sets.append("done = %s")
        params.append(done)
        changed.append("done")
        # set completed_at when flipping to done, clear when reopening
        sets.append("completed_at = %s")
        params.append(_now() if done and not current["done"] else (None if not done else current["completed_at"]))
        changed.append("completed_at")
    if sets:
        undo.record("update", "todos", todo_id, {c: prior[c] for c in changed}, session_id=getattr(g, "session_id", "default"))
        execute(f"UPDATE todos SET {','.join(sets)} WHERE id = %s", params + [todo_id])
    return get_todo(todo_id)


def delete_todo(todo_id: int) -> bool:
    row = _raw(todo_id)
    if row is None:
        return False
    undo.record("restore", "todos", None, dict(row), session_id=getattr(g, "session_id", "default"))
    return execute("DELETE FROM todos WHERE id = %s", (todo_id,)).rowcount > 0
