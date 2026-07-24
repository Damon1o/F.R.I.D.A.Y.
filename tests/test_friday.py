"""Phase 2 F.R.I.D.A.Y. assistant: tools, agent loop, persistence, endpoints. LLM always faked."""
import json

import pytest

from core.llm import LLMError
from pages.friday import agent, messages, tools
from pages.friday.tools import dispatch
from pages.todos import models as todos


class FakeClient:
    """Returns scripted assistant messages in order; records the calls it saw."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        return self.scripted.pop(0)


def _tool_call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def _run(text, client):
    return list(agent.run_turn(text, client))


# ---- tools dispatch ----

def test_dispatch_creates_todo(ctx):
    r = dispatch("create_todo", {"title": "Buy milk"})
    assert r["id"] and r["title"] == "Buy milk"


def test_dispatch_validation_error_is_returned(ctx):
    assert "error" in dispatch("create_todo", {"title": ""})


def test_dispatch_missing_row(ctx):
    assert dispatch("delete_todo", {"todo_id": 999}) == {"error": "todo not found"}


def test_dispatch_unknown_tool(ctx):
    assert "unknown tool" in dispatch("frobnicate", {})["error"]


# ---- music tools ----

class FakeProvider:
    """Records the last control action / play query; fails on sentinel inputs."""
    def __init__(self):
        self.controlled = None
        self.played = None

    def control(self, action, position_ms=None):
        self.controlled = action
        return action != "boom"

    def play_track(self, query):
        self.played = query
        return query != "nope"


@pytest.fixture
def fake_music(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(tools, "get_provider", lambda service="spotify": fake)
    return fake


def test_dispatch_control_music(fake_music):
    assert dispatch("control_music", {"action": "next"}) == {"ok": True}
    assert fake_music.controlled == "next"


def test_dispatch_control_music_failure_reports_not_ok(fake_music):
    assert dispatch("control_music", {"action": "boom"}) == {"ok": False}


def test_dispatch_control_music_missing_action(fake_music):
    assert "error" in dispatch("control_music", {})


def test_dispatch_play_track(fake_music):
    assert dispatch("play_track", {"query": "Bohemian Rhapsody"}) == {"playing": True}
    assert fake_music.played == "Bohemian Rhapsody"


def test_dispatch_play_track_no_match_reports_not_playing(fake_music):
    assert dispatch("play_track", {"query": "nope"}) == {"playing": False}


def test_dispatch_play_track_missing_query(fake_music):
    assert "error" in dispatch("play_track", {})


# ---- agent loop ----

def test_loop_runs_tool_then_streams_reply(ctx):
    fake = FakeClient([
        {"role": "assistant", "content": None,
         "tool_calls": [_tool_call("create_todo", {"title": "Buy milk"})]},
        {"role": "assistant", "content": "Added Buy milk to your tasks."},
    ])
    frames = _run("add buy milk", fake)
    events = [e for e, _ in frames]

    assert events[0] == "status"
    assert "token" in events
    assert events[-1] == "done"
    text = "".join(p["text"] for e, p in frames if e == "token").strip()
    assert text == "Added Buy milk to your tasks."

    assert any(t["title"] == "Buy milk" for t in todos.list_todos())
    roles = [m["role"] for m in messages.history()]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_loop_no_api_key_errors_gracefully(ctx):
    # Default client reads the empty test config key and raises "no API key".
    frames = _run("do something", None)
    assert frames[-1][0] == "done"
    assert any(e == "error" and "DEEPSEEK_API_KEY" in p["text"] for e, p in frames)
    # user turn still recorded, no crash
    assert [m["role"] for m in messages.history()] == ["user"]


def test_loop_step_cap(ctx):
    # Always returns a tool call → never terminates; loop must stop and error.
    fake = FakeClient([
        {"role": "assistant", "content": None,
         "tool_calls": [_tool_call("list_todos", {})]}
        for _ in range(agent.MAX_STEPS)
    ])
    frames = _run("loop forever", fake)
    assert any(e == "error" for e, _ in frames)
    assert frames[-1][0] == "done"


# ---- persistence ----

def test_history_and_clear(ctx):
    messages.add("user", "hi")
    messages.add("assistant", "hello")
    assert [m["content"] for m in messages.history()] == ["hi", "hello"]
    messages.clear()
    assert messages.history() == []


def test_to_api_shapes_tool_messages(ctx):
    tc = [_tool_call("list_todos", {})]
    messages.add("user", "check tasks")
    messages.add("assistant", None, tool_calls=tc)
    messages.add("tool", "[]", tool_call_id="c1", name="list_todos")
    api = messages.to_api()
    assert api[1]["tool_calls"] == tc
    assert api[2] == {"role": "tool", "tool_call_id": "c1", "name": "list_todos", "content": "[]"}


# ---- endpoints ----

def test_message_endpoint_streams(client, monkeypatch):
    fake = FakeClient([{"role": "assistant", "content": "Hi there."}])
    monkeypatch.setattr(agent, "DeepSeekClient", lambda *a, **k: fake)
    res = client.post("/api/friday/message", json={"text": "hello"})
    body = res.data.decode()
    assert res.mimetype == "text/event-stream"
    assert "event: token" in body and "event: done" in body


def test_message_endpoint_rejects_empty(client):
    assert client.post("/api/friday/message", json={"text": "  "}).status_code == 400


def test_history_and_clear_endpoints(client, monkeypatch):
    fake = FakeClient([{"role": "assistant", "content": "Done."}])
    monkeypatch.setattr(agent, "DeepSeekClient", lambda *a, **k: fake)
    client.post("/api/friday/message", json={"text": "hello"})

    hist = client.get("/api/friday/history").get_json()
    assert [m["role"] for m in hist] == ["user", "assistant"]

    assert client.post("/api/friday/clear").status_code == 204
    assert client.get("/api/friday/history").get_json() == []
