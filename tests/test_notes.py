"""Spec I notes: model CRUD + search, /api/notes endpoints, and remember/recall tools."""
from pages.notes import models as notes
from pages.friday.tools import dispatch


# ---- model ----

def test_create_and_list(ctx):
    n = notes.create_note("parking spot is B12")
    assert n["id"] and n["text"] == "parking spot is B12"
    assert [x["text"] for x in notes.list_notes()] == ["parking spot is B12"]


def test_create_blank_raises(ctx):
    from pages.calendar.models import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        notes.create_note("   ")


def test_search_matches_substring_case_insensitive(ctx):
    notes.create_note("Kate's birthday is March 3")
    notes.create_note("wifi password is hunter2")
    assert [n["text"] for n in notes.search_notes("BIRTHDAY")] == ["Kate's birthday is March 3"]
    assert notes.search_notes("nomatch") == []
    assert notes.search_notes("  ") == []


def test_delete(ctx):
    n = notes.create_note("temp")
    assert notes.delete_note(n["id"]) is True
    assert notes.delete_note(n["id"]) is False


# ---- tools ----

def test_remember_and_recall_tools(ctx):
    assert dispatch("remember", {"text": "dentist at 3pm friday"})["text"] == "dentist at 3pm friday"
    hits = dispatch("recall", {"query": "dentist"})
    assert len(hits) == 1 and hits[0]["text"] == "dentist at 3pm friday"


def test_list_notes_tool(ctx):
    notes.create_note("a")
    assert len(dispatch("list_notes", {})) == 1


def test_delete_note_tool_missing(ctx):
    assert dispatch("delete_note", {"note_id": 999}) == {"error": "note not found"}


# ---- endpoints ----

def test_notes_api_crud(client):
    created = client.post("/api/notes", json={"text": "buy cables"}).get_json()
    assert created["text"] == "buy cables"
    assert client.get("/api/notes").get_json()[0]["text"] == "buy cables"
    assert client.get("/api/notes?q=cables").get_json()[0]["id"] == created["id"]
    assert client.get("/api/notes?q=zzz").get_json() == []
    assert client.delete(f"/api/notes/{created['id']}").status_code == 204


def test_notes_api_rejects_blank(client):
    assert client.post("/api/notes", json={"text": ""}).status_code == 400


def test_notes_page_renders(client):
    assert client.get("/notes").status_code == 200
