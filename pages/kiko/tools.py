"""LLM tool schemas + dispatch to the existing Phase 1 model functions.

No DB logic here — every tool wraps a calendar/todo model call. A tool that raises
ValidationError returns {"error": ...} so the LLM can self-correct mid-turn.
"""
from pages.calendar import models as events
from pages.calendar.models import ValidationError
from pages.todos import models as todos

_DT = "ISO-8601 datetime, e.g. 2026-07-24T15:00:00. Assume the user's local time."


def _fn(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOLS = [
    _fn("create_event", "Create a calendar event.", {
        "title": {"type": "string"},
        "start_at": {"type": "string", "description": _DT},
        "end_at": {"type": "string", "description": _DT},
        "all_day": {"type": "boolean"},
        "location": {"type": "string"},
        "notes": {"type": "string"},
    }, ["title", "start_at"]),
    _fn("update_event", "Edit an existing event by id. Only pass fields to change.", {
        "event_id": {"type": "integer"},
        "title": {"type": "string"},
        "start_at": {"type": "string", "description": _DT},
        "end_at": {"type": "string", "description": _DT},
        "all_day": {"type": "boolean"},
        "location": {"type": "string"},
        "notes": {"type": "string"},
    }, ["event_id"]),
    _fn("delete_event", "Delete an event by id.", {
        "event_id": {"type": "integer"},
    }, ["event_id"]),
    _fn("list_events", "List events, optionally within an ISO-8601 date range.", {
        "start": {"type": "string", "description": _DT},
        "end": {"type": "string", "description": _DT},
    }, []),
    _fn("create_todo", "Create a to-do task.", {
        "title": {"type": "string"},
        "due_at": {"type": "string", "description": _DT},
        "notes": {"type": "string"},
    }, ["title"]),
    _fn("update_todo", "Edit a to-do by id. Set done=true to complete it.", {
        "todo_id": {"type": "integer"},
        "title": {"type": "string"},
        "due_at": {"type": "string", "description": _DT},
        "notes": {"type": "string"},
        "done": {"type": "boolean"},
    }, ["todo_id"]),
    _fn("delete_todo", "Delete a to-do by id.", {
        "todo_id": {"type": "integer"},
    }, ["todo_id"]),
    _fn("list_todos", "List to-dos. Pass done=false for open tasks only.", {
        "done": {"type": "boolean"},
    }, []),
]


def dispatch(name: str, args: dict):
    """Run tool `name` with `args`; return a JSON-serialisable result."""
    try:
        if name == "create_event":
            return events.create_event(args)
        if name == "update_event":
            r = events.update_event(args.pop("event_id"), args)
            return r or {"error": "event not found"}
        if name == "delete_event":
            ok = events.delete_event(args["event_id"])
            return {"deleted": ok} if ok else {"error": "event not found"}
        if name == "list_events":
            return events.list_events(args.get("start"), args.get("end"))
        if name == "create_todo":
            return todos.create_todo(args)
        if name == "update_todo":
            r = todos.update_todo(args.pop("todo_id"), args)
            return r or {"error": "todo not found"}
        if name == "delete_todo":
            ok = todos.delete_todo(args["todo_id"])
            return {"deleted": ok} if ok else {"error": "todo not found"}
        if name == "list_todos":
            return todos.list_todos(args.get("done"))
        return {"error": f"unknown tool {name}"}
    except ValidationError as e:
        return {"error": str(e)}
    except KeyError as e:
        return {"error": f"missing argument {e}"}
