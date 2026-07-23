"""Spec B voice: run_text agent helper, STT/TTS wrappers, and the /api/voice endpoint. LLM + binaries always faked."""
import io
import json

from pages.friday import agent, messages


class FakeClient:
    """Returns scripted assistant messages in order (mirrors tests/test_friday.py)."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        return self.scripted.pop(0)


def _tool_call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def test_run_text_runs_tool_then_returns_reply(ctx):
    fake = FakeClient([
        {"role": "assistant", "content": None,
         "tool_calls": [_tool_call("create_todo", {"title": "Buy milk"})]},
        {"role": "assistant", "content": "Added Buy milk to your tasks."},
    ])
    result = agent.run_text("add buy milk", fake)
    assert result["reply"] == "Added Buy milk to your tasks."
    assert result["actions"] == ["create_todo"]
    roles = [m["role"] for m in messages.history()]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_run_text_no_api_key_returns_spoken_error(ctx):
    result = agent.run_text("do something", None)
    assert "DEEPSEEK_API_KEY" in result["reply"]
    assert result["actions"] == []
    assert [m["role"] for m in messages.history()] == ["user"]
