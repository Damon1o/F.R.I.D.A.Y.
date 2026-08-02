import pytest

from pages.calendar.models import ValidationError
from pages.todos import models


def test_create_and_empty_title(ctx):
    t = models.create_todo({"title": "Buy milk"})
    assert t["id"] and t["done"] is False and t["completed_at"] is None
    with pytest.raises(ValidationError):
        models.create_todo({"title": ""})


def test_done_toggle_sets_and_clears_completed_at(ctx):
    t = models.create_todo({"title": "Task"})
    done = models.update_todo(t["id"], {"done": True})
    assert done["done"] is True and done["completed_at"] is not None
    reopened = models.update_todo(t["id"], {"done": False})
    assert reopened["done"] is False and reopened["completed_at"] is None


def test_done_filter(ctx):
    a = models.create_todo({"title": "open"})
    b = models.create_todo({"title": "closed"})
    models.update_todo(b["id"], {"done": True})
    assert [t["title"] for t in models.list_todos(done=False)] == ["open"]
    assert [t["title"] for t in models.list_todos(done=True)] == ["closed"]


def test_delete(ctx):
    t = models.create_todo({"title": "gone"})
    assert models.delete_todo(t["id"]) is True
    assert models.get_todo(t["id"]) is None


def test_reorder_beats_due_date_and_survives_new_todos(ctx):
    a = models.create_todo({"title": "a", "due_at": "2030-01-01T09:00"})
    b = models.create_todo({"title": "b", "due_at": "2030-01-02T09:00"})
    assert [t["title"] for t in models.list_todos()] == ["a", "b"]
    models.reorder([b["id"], a["id"]])
    assert [t["title"] for t in models.list_todos()] == ["b", "a"]
    # position 0 is "never dragged", so a fresh todo sorts ahead of both.
    models.create_todo({"title": "c"})
    assert [t["title"] for t in models.list_todos()] == ["c", "b", "a"]


def test_reorder_keeps_done_todos_at_the_bottom(ctx):
    a = models.create_todo({"title": "a"})
    b = models.create_todo({"title": "b"})
    models.update_todo(a["id"], {"done": True})
    models.reorder([a["id"], b["id"]])
    assert [t["title"] for t in models.list_todos()] == ["b", "a"]


def test_reorder_api(client):
    first = client.post("/api/todos", json={"title": "first"}).get_json()["id"]
    second = client.post("/api/todos", json={"title": "second"}).get_json()["id"]
    assert client.post("/api/todos/reorder", json={"ids": [second, first]}).status_code == 204
    assert [t["title"] for t in client.get("/api/todos").get_json()] == ["second", "first"]
    assert client.post("/api/todos/reorder", json={"ids": "nope"}).status_code == 400
    assert client.post("/api/todos/reorder", json={"ids": ["x"]}).status_code == 400


def test_api_crud(client):
    r = client.post("/api/todos", json={"title": "Ship"})
    assert r.status_code == 201
    tid = r.get_json()["id"]
    assert client.patch(f"/api/todos/{tid}", json={"done": True}).get_json()["done"] is True
    assert client.get("/api/todos?done=1").status_code == 200
    assert client.delete(f"/api/todos/{tid}").status_code == 204
    assert client.post("/api/todos", json={"title": ""}).status_code == 400
