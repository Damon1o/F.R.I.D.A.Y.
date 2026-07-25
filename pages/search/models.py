"""Spec Q — one query across events, todos, and notes. ILIKE (single user, small data)."""
from core.db import query
from pages.calendar.models import to_dict as event_dict
from pages.todos.models import to_dict as todo_dict
from pages.notes.models import to_dict as note_dict

_LIMIT = 25


def search(q: str) -> dict:
    q = (q or "").strip()
    if not q:
        return {"events": [], "todos": [], "notes": []}
    like = f"%{q}%"
    events = query(
        "SELECT * FROM events WHERE title ILIKE %s OR location ILIKE %s OR notes ILIKE %s "
        "ORDER BY start_at LIMIT %s", (like, like, like, _LIMIT))
    todos = query(
        "SELECT * FROM todos WHERE title ILIKE %s OR notes ILIKE %s "
        "ORDER BY done, created_at LIMIT %s", (like, like, _LIMIT))
    notes = query(
        "SELECT * FROM notes WHERE text ILIKE %s ORDER BY created_at DESC LIMIT %s", (like, _LIMIT))
    return {
        "events": [event_dict(r) for r in events],
        "todos": [todo_dict(r) for r in todos],
        "notes": [note_dict(r) for r in notes],
    }
