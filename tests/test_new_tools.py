"""Spec K quick-add endpoint + Spec O get_now_playing tool. LLM/provider faked."""
import json

from pages.friday import agent, tools
from pages.friday.tools import dispatch
from pages.music import TrackInfo


class FakeClient:
    def __init__(self, scripted):
        self.scripted = list(scripted)

    def complete(self, messages, tools=None):
        return self.scripted.pop(0)


def _tool_call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


# ---- Spec K: quick-add ----

def test_quickadd_runs_agent_and_creates(client, monkeypatch):
    fake = FakeClient([
        {"role": "assistant", "content": None,
         "tool_calls": [_tool_call("create_todo", {"title": "buy cables"})]},
        {"role": "assistant", "content": "Added buy cables."},
    ])
    monkeypatch.setattr(agent, "DeepSeekClient", lambda *a, **k: fake)
    res = client.post("/api/quickadd", json={"text": "todo buy cables"}).get_json()
    assert res["reply"] == "Added buy cables."
    assert "create_todo" in res["actions"]


def test_quickadd_rejects_empty(client):
    assert client.post("/api/quickadd", json={"text": "  "}).status_code == 400


# ---- Spec O: now playing ----

class FakeProvider:
    def __init__(self, track):
        self._track = track

    def get_now_playing(self):
        return self._track


def test_get_now_playing_returns_track(ctx, monkeypatch):
    track = TrackInfo(title="Song", artist="Artist", album_art=None,
                      progress_ms=1000, duration_ms=200000, is_playing=True)
    monkeypatch.setattr(tools, "get_provider", lambda service="spotify": FakeProvider(track))
    r = dispatch("get_now_playing", {})
    assert r["title"] == "Song" and r["artist"] == "Artist" and r["is_playing"] is True


def test_get_now_playing_nothing(ctx, monkeypatch):
    monkeypatch.setattr(tools, "get_provider", lambda service="spotify": FakeProvider(None))
    assert dispatch("get_now_playing", {}) == {"playing": False}
