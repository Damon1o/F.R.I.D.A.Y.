"""Phase 2 F.R.I.D.A.Y. assistant: tools, agent loop, persistence, endpoints. LLM always faked."""
import json

import pytest

from core.llm import LLMError
from pages.friday import agent, messages, search_web, tools
from pages.friday.tools import dispatch
from pages.todos import models as todos


class FakeClient:
    """Returns scripted assistant messages in order; records the calls it saw."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        # run_turn makes one extra tool-free call to auto-title a new thread; scripts
        # in these tests only cover the reply, so anything past the script is a title.
        if not self.scripted:
            return {"role": "assistant", "content": "Scripted Chat Title"}
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


# ---- streaming ----

class StreamClient:
    """Emits scripted deltas the way DeepSeek does, so run_turn takes the stream path."""
    def __init__(self, deltas, tool_calls=None):
        self.deltas = list(deltas)
        self.tool_calls = tool_calls

    def complete(self, messages, tools=None):     # auto-title call
        return {"role": "assistant", "content": "Scripted Chat Title"}

    def stream(self, messages, tools=None):
        msg = {"role": "assistant", "content": ""}
        if self.tool_calls:
            calls, self.tool_calls = self.tool_calls, None
            msg["tool_calls"] = calls
            return msg
        for d in self.deltas:
            msg["content"] += d
            yield d
        return msg


def test_run_turn_forwards_real_deltas(ctx):
    frames = list(agent.run_turn("hi", StreamClient(["Hel", "lo ", "sir."])))
    assert [p["text"] for e, p in frames if e == "token"] == ["Hel", "lo ", "sir."]
    assert messages.history()[-1]["content"] == "Hello sir."


def test_stream_parses_sse_and_reassembles_split_tool_call(app, monkeypatch):
    import io
    from core.llm import DeepSeekClient

    body = (b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n'
            b'\n'                                      # keep-alive blank line
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1",'
            b'"function":{"name":"list_","arguments":"{"}}]}}]}\n'
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            b'"function":{"name":"todos","arguments":"}"}}]}}]}\n'
            b'data: [DONE]\n')

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Resp(body))
    with app.app_context():
        gen = DeepSeekClient(api_key="k").stream([{"role": "user", "content": "hi"}])
        deltas = []
        try:
            while True:
                deltas.append(next(gen))
        except StopIteration as stop:
            msg = stop.value
    assert deltas == ["Hi"]
    assert msg["content"] == "Hi"
    assert msg["tool_calls"] == [{"id": "c1", "type": "function",
                                  "function": {"name": "list_todos", "arguments": "{}"}}]


def test_interrupt_midstream_keeps_partial_reply(ctx):
    """Stop button / barge-in aborts the SSE fetch, which closes this generator."""
    gen = agent.run_turn("hi", StreamClient(["Hel", "lo ", "sir."]))
    assert next(gen) == ("token", {"text": "Hel"})
    gen.close()
    last = messages.history()[-1]
    assert last["role"] == "assistant" and last["content"] == "Hel"


# ---- voice notes (Spec V) ----

def test_take_note_stores_text_verbatim(ctx):
    spoken = "Remind Kate that the Q3 numbers are WRONG -- recheck row 14."
    assert dispatch("take_note", {"text": spoken})["text"] == spoken


def test_take_note_missing_text_returns_error(ctx):
    assert "error" in dispatch("take_note", {})


# ---- web search (Spec H) ----

SERP_JSON = {"organic_results": [
    {"title": "Result A", "link": "https://a.example", "snippet": "snippet a"},
    {"title": "Result B", "link": "https://b.example", "snippet": "snippet b"},
]}


class FakeResp:
    def __init__(self, payload):
        self.payload = payload
        self.seen = {}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


@pytest.fixture
def serp(monkeypatch):
    """Key set + canned SerpAPI JSON; records the params the module sent."""
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    sent = {}

    def fake_get(url, **kw):
        sent.update(kw.get("params") or {})
        return FakeResp(SERP_JSON)

    monkeypatch.setattr(search_web.requests, "get", fake_get)
    return sent


def test_search_web_maps_results(serp):
    assert dispatch("search_web", {"query": "python 3.14"}) == [
        {"title": "Result A", "url": "https://a.example", "snippet": "snippet a"},
        {"title": "Result B", "url": "https://b.example", "snippet": "snippet b"},
    ]
    assert serp["q"] == "python 3.14" and serp["num"] == 5
    assert serp["api_key"] == "test-key"


def test_search_web_clamps_count(serp):
    dispatch("search_web", {"query": "x", "count": 99})
    assert serp["num"] == 10
    dispatch("search_web", {"query": "x", "count": 0})
    assert serp["num"] == 1


def test_search_web_without_key_returns_error(monkeypatch):
    monkeypatch.delenv("SERP_API_KEY", raising=False)
    assert "error" in dispatch("search_web", {"query": "x"})


def test_search_web_reports_provider_error_body(monkeypatch):
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setattr(search_web.requests, "get",
                        lambda url, **kw: FakeResp({"error": "Invalid API key"}))
    assert "Invalid API key" in dispatch("search_web", {"query": "x"})["error"]


def test_search_web_provider_failure_returns_error(monkeypatch):
    monkeypatch.setenv("SERP_API_KEY", "test-key")

    def boom(url, **kw):
        raise search_web.requests.Timeout("timed out")

    monkeypatch.setattr(search_web.requests, "get", boom)
    assert "search failed" in dispatch("search_web", {"query": "x"})["error"]


# ---- Spec AD: retry / edit rewind ----

def test_truncate_from_drops_the_row_and_everything_after(ctx):
    messages.add("user", "one")
    messages.add("assistant", "reply one")
    messages.add("user", "two")
    messages.add("assistant", "reply two")
    rows = messages.history()
    messages.truncate_from(rows[2]["id"])
    left = [(m["role"], m["content"]) for m in messages.history()]
    assert left == [("user", "one"), ("assistant", "reply one")]


def test_truncate_from_leaves_other_threads_alone(ctx):
    messages.add("user", "thread one")
    first = messages.history()[0]["id"]
    messages.new_thread()
    messages.add("user", "thread two")
    messages.truncate_from(first)          # id belongs to the *other* thread
    assert [m["content"] for m in messages.history()] == ["thread two"]


def test_truncate_takes_tool_rows_with_the_assistant_turn(ctx):
    """An orphan tool_call_id makes the next API call invalid — the rewind has to
    remove a turn's tool rows along with the assistant message that requested them."""
    call = _tool_call("create_todo", {"title": "x"})
    messages.add("user", "add x")
    messages.add("assistant", None, tool_calls=[call])
    messages.add("tool", json.dumps({"id": 1}), tool_call_id="c1", name="create_todo")
    messages.add("assistant", "Added x.")
    assistant_row = messages.history()[1]["id"]
    messages.truncate_from(assistant_row)
    replay = messages.to_api()
    assert not [m for m in replay if m["role"] == "tool"]
    assert [m["role"] for m in replay] == ["user"]


def test_truncate_endpoint_returns_last_surviving_id(client, app):
    with app.app_context(), app.test_request_context():
        messages.add("user", "one")
        messages.add("assistant", "reply")
        rows = messages.history()
    res = client.delete(f"/api/friday/history/{rows[1]['id']}")
    assert res.status_code == 200
    assert res.get_json()["last"] == rows[0]["id"]


def test_truncate_endpoint_on_missing_id_is_a_noop(client):
    assert client.delete("/api/friday/history/99999").status_code == 200


# ---- Spec AE: tool-call transparency ----

def test_tool_frame_is_emitted_with_a_safe_summary(ctx):
    client = FakeClient([
        {"role": "assistant", "tool_calls": [_tool_call("create_todo", {"title": "Buy milk"})]},
        {"role": "assistant", "content": "Added it."},
    ])
    frames = _run("add buy milk", client)
    tool_frames = [p for e, p in frames if e == "tool"]
    assert tool_frames == [{"name": "create_todo", "summary": "Buy milk"}]


def test_tool_summary_is_truncated_and_survives_bad_arguments():
    long = _tool_call("search_web", {"query": "x" * 200})
    assert len(agent.tool_notes([long])[0]["summary"]) == 80
    broken = {"id": "c1", "type": "function",
              "function": {"name": "list_events", "arguments": "{not json"}}
    assert agent.tool_notes([broken]) == [{"name": "list_events", "summary": ""}]


def test_tool_results_never_reach_the_stream(ctx, monkeypatch):
    """Tool results are untrusted third-party text. They belong in the model's
    context and nowhere else — least of all rendered in the UI."""
    monkeypatch.setattr("pages.friday.agent.dispatch",
                        lambda name, args: {"note": "SENTINEL-LEAK"})
    client = FakeClient([
        {"role": "assistant", "tool_calls": [_tool_call("search_web", {"query": "hi"})]},
        {"role": "assistant", "content": "Done."},
    ])
    assert "SENTINEL-LEAK" not in json.dumps(_run("search hi", client))


def test_history_projects_tool_notes_onto_the_reply(client, app):
    with app.app_context(), app.test_request_context():
        messages.add("user", "what's on")
        messages.add("assistant", None, tool_calls=[_tool_call("list_events", {})])
        messages.add("tool", json.dumps([]), tool_call_id="c1", name="list_events")
        messages.add("assistant", "Nothing today.")
    rows = client.get("/api/friday/history").get_json()
    assert rows[-1]["tools"] == [{"name": "list_events", "summary": ""}]
    assert rows[0]["tools"] == []          # the user turn carries none
