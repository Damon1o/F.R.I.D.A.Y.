"""Spec I — free-form notes FRIDAY can remember + recall. ILIKE search (single user)."""
from flask import g
from core import undo
from core.db import execute, query
from pages.calendar.models import ValidationError


def to_dict(row) -> dict:
    return dict(row)


def list_notes(limit: int | None = None, offset: int = 0) -> list[dict]:
    """Newest first. `limit` pages the list; None returns everything (agent recall)."""
    sql = "SELECT * FROM notes ORDER BY created_at DESC, id DESC"
    params: list = []
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params += [limit, offset]
    return [to_dict(r) for r in query(sql, tuple(params))]


def count_notes() -> int:
    return query("SELECT count(*) AS n FROM notes", one=True)["n"]


def get_note(note_id: int):
    row = query("SELECT * FROM notes WHERE id = %s", (note_id,), one=True)
    return to_dict(row) if row else None


def create_note(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValidationError("text is required")
    row = execute("INSERT INTO notes (text) VALUES (%s) RETURNING id", (text,)).fetchone()
    undo.record("delete", "notes", row["id"], session_id=getattr(g, "session_id", "default"))
    return get_note(row["id"])


def search_notes(q: str, limit: int = 10) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    rows = query(
        "SELECT * FROM notes WHERE text ILIKE %s ORDER BY created_at DESC, id DESC LIMIT %s",
        (f"%{q}%", limit),
    )
    return [to_dict(r) for r in rows]


def delete_note(note_id: int) -> bool:
    row = query("SELECT * FROM notes WHERE id = %s", (note_id,), one=True)
    if row is None:
        return False
    undo.record("restore", "notes", None, dict(row), session_id=getattr(g, "session_id", "default"))
    return execute("DELETE FROM notes WHERE id = %s", (note_id,)).rowcount > 0
