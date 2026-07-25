"""Spec Q — unified search across events, todos, notes: model, endpoint, tool."""
from pages.calendar import models as events
from pages.todos import models as todos
from pages.notes import models as notes
from pages.search import models as search
from pages.friday.tools import dispatch


def _seed():
    events.create_event({"title": "Dentist appointment", "start_at": "2026-07-25T09:00:00"})
    todos.create_todo({"title": "Call dentist office"})
    notes.create_note("dentist is on Main St")
    todos.create_todo({"title": "buy milk"})


def test_search_spans_all_sources(ctx):
    _seed()
    r = search.search("dentist")
    assert len(r["events"]) == 1 and len(r["todos"]) == 1 and len(r["notes"]) == 1
    assert r["events"][0]["title"] == "Dentist appointment"


def test_search_no_match(ctx):
    _seed()
    r = search.search("xyzzy")
    assert r == {"events": [], "todos": [], "notes": []}


def test_search_blank_query(ctx):
    assert search.search("  ") == {"events": [], "todos": [], "notes": []}


def test_search_api(client, ctx):
    _seed()
    r = client.get("/api/search?q=dentist").get_json()
    assert len(r["todos"]) == 1


def test_search_all_tool(ctx):
    _seed()
    r = dispatch("search_all", {"query": "milk"})
    assert [t["title"] for t in r["todos"]] == ["buy milk"]
