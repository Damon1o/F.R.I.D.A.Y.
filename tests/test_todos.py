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


def test_api_crud(client):
    r = client.post("/api/todos", json={"title": "Ship"})
    assert r.status_code == 201
    tid = r.get_json()["id"]
    assert client.patch(f"/api/todos/{tid}", json={"done": True}).get_json()["done"] is True
    assert client.get("/api/todos?done=1").status_code == 200
    assert client.delete(f"/api/todos/{tid}").status_code == 204
    assert client.post("/api/todos", json={"title": ""}).status_code == 400
