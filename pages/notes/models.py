"""Spec I — free-form notes FRIDAY can remember + recall. ILIKE search (single user)."""
from core.db import execute, query
from pages.calendar.models import ValidationError


def to_dict(row) -> dict:
    return dict(row)


def list_notes() -> list[dict]:
    return [to_dict(r) for r in query("SELECT * FROM notes ORDER BY created_at DESC, id DESC")]


def get_note(note_id: int):
    row = query("SELECT * FROM notes WHERE id = %s", (note_id,), one=True)
    return to_dict(row) if row else None


def create_note(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValidationError("text is required")
    row = execute("INSERT INTO notes (text) VALUES (%s) RETURNING id", (text,)).fetchone()
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
    return execute("DELETE FROM notes WHERE id = %s", (note_id,)).rowcount > 0
