"""Todo row <-> dict, validation, and DB queries."""
from datetime import datetime, timezone

from core.db import execute, query
from pages.calendar.models import ValidationError, _parse_iso


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    return d


def list_todos(done=None) -> list[dict]:
    sql = "SELECT * FROM todos"
    params = []
    if done is not None:
        sql += " WHERE done = ?"
        params.append(1 if done else 0)
    # open first, then by due date (nulls last), newest created last
    sql += " ORDER BY done, due_at IS NULL, due_at, created_at"
    return [to_dict(r) for r in query(sql, params)]


def get_todo(todo_id: int):
    row = query("SELECT * FROM todos WHERE id = ?", (todo_id,), one=True)
    return to_dict(row) if row else None


def create_todo(data: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValidationError("title is required")
    due_at = data.get("due_at")
    if due_at:
        due_at = _parse_iso(due_at, "due_at").isoformat()
    cur = execute(
        "INSERT INTO todos (title, due_at, notes) VALUES (?, ?, ?)",
        (title, due_at or None, data.get("notes") or None),
    )
    return get_todo(cur.lastrowid)


def update_todo(todo_id: int, data: dict):
    current = get_todo(todo_id)
    if current is None:
        return None
    sets, params = [], []
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("title is required")
        sets.append("title = ?")
        params.append(title)
    if "due_at" in data:
        due = data["due_at"]
        due = _parse_iso(due, "due_at").isoformat() if due else None
        sets.append("due_at = ?")
        params.append(due)
    if "notes" in data:
        sets.append("notes = ?")
        params.append(data["notes"] or None)
    if "done" in data:
        done = 1 if data["done"] else 0
        sets.append("done = ?")
        params.append(done)
        # set completed_at when flipping to done, clear when reopening
        sets.append("completed_at = ?")
        params.append(_now() if done and not current["done"] else (None if not done else current["completed_at"]))
    if sets:
        execute(f"UPDATE todos SET {','.join(sets)} WHERE id = ?", params + [todo_id])
    return get_todo(todo_id)


def delete_todo(todo_id: int) -> bool:
    return execute("DELETE FROM todos WHERE id = ?", (todo_id,)).rowcount > 0
