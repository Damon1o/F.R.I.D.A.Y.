"""Spec R — single tag per todo: model filter, list_tags, endpoints, tool params."""
from pages.todos import models as todos
from pages.friday.tools import dispatch


def test_create_with_tag_and_filter(ctx):
    todos.create_todo({"title": "ship", "tag": "work"})
    todos.create_todo({"title": "milk", "tag": "home"})
    todos.create_todo({"title": "untagged"})
    assert [t["title"] for t in todos.list_todos(tag="work")] == ["ship"]
    assert len(todos.list_todos()) == 3


def test_list_tags_distinct(ctx):
    todos.create_todo({"title": "a", "tag": "work"})
    todos.create_todo({"title": "b", "tag": "work"})
    todos.create_todo({"title": "c", "tag": "home"})
    assert todos.list_tags() == ["home", "work"]


def test_update_sets_tag(ctx):
    t = todos.create_todo({"title": "x"})
    todos.update_todo(t["id"], {"tag": "errands"})
    assert todos.get_todo(t["id"])["tag"] == "errands"


def test_api_tag_filter_and_tags(client):
    client.post("/api/todos", json={"title": "ship", "tag": "work"})
    client.post("/api/todos", json={"title": "milk", "tag": "home"})
    assert [t["title"] for t in client.get("/api/todos?tag=work").get_json()] == ["ship"]
    assert client.get("/api/tags").get_json() == ["home", "work"]


def test_tool_create_and_list_by_tag(ctx):
    dispatch("create_todo", {"title": "deploy", "tag": "work"})
    assert [t["title"] for t in dispatch("list_todos", {"tag": "work"})] == ["deploy"]
