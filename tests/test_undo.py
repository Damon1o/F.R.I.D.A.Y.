"""Spec S — single-level undo across events, todos, notes: model + endpoint + tool."""
from core import undo
from pages.calendar import models as events
from pages.todos import models as todos
from pages.notes import models as notes
from pages.friday.tools import dispatch


def test_undo_create_removes(ctx):
    t = todos.create_todo({"title": "oops"})
    assert undo.undo()["undone"] == "delete"
    assert todos.get_todo(t["id"]) is None


def test_undo_delete_restores(ctx):
    n = notes.create_note("keep me")
    notes.delete_note(n["id"])
    undo.undo()
    assert any(x["text"] == "keep me" for x in notes.list_notes())


def test_undo_update_restores_prior(ctx):
    t = todos.create_todo({"title": "before"})
    todos.update_todo(t["id"], {"title": "after"})
    undo.undo()
    assert todos.get_todo(t["id"])["title"] == "before"


def test_undo_event_update(ctx):
    e = events.create_event({"title": "orig", "start_at": "2026-07-20T09:00:00"})
    events.update_event(e["id"], {"title": "changed"})
    undo.undo()
    assert events.get_event(e["id"])["title"] == "orig"


def test_only_latest_is_undoable(ctx):
    a = todos.create_todo({"title": "A"})
    b = todos.create_todo({"title": "B"})
    undo.undo()  # undoes creation of B only
    assert todos.get_todo(b["id"]) is None
    assert todos.get_todo(a["id"]) is not None
    assert undo.undo() == {"error": "nothing to undo"}


def test_nothing_to_undo(ctx):
    assert undo.undo() == {"error": "nothing to undo"}


def test_undo_endpoint_and_tool(ctx, client):
    todos.create_todo({"title": "viaendpoint"})
    assert client.post("/api/undo").get_json()["undone"] == "delete"
    todos.create_todo({"title": "viatool"})
    assert dispatch("undo_last", {})["undone"] == "delete"
