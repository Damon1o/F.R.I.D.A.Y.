"""Server-side tool-calling loop. Yields SSE frames (event, payload)."""
import json

from core.llm import DeepSeekClient, LLMError
from pages.kiko import messages
from pages.kiko.tools import TOOLS, dispatch

MAX_STEPS = 6  # guard against a runaway tool loop


def _system() -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    return {"role": "system", "content": (
        "You are Kiko, a concise personal productivity assistant. "
        f"The current local datetime is {now}. "
        "Use the tools to create, edit, delete or list the user's events and todos. "
        "Act immediately — do not ask for confirmation. Resolve relative dates "
        "(tomorrow, Friday) to concrete ISO-8601 datetimes. After acting, reply in one "
        "short sentence describing what you did."
    )}


def _chunks(text: str):
    """Pace a fully-received reply into word chunks for a streamed feel."""
    for word in text.split(" "):
        if word:
            yield word + " "


def _args(tool_call) -> dict:
    try:
        return json.loads(tool_call["function"].get("arguments") or "{}")
    except ValueError:
        return {}


def run_turn(user_text: str, client=None):
    """Persist the user turn, drive the loop, yield (event, payload) frames."""
    client = client or DeepSeekClient()
    messages.add("user", user_text)
    # Note: no yield inside a finally — a disconnected client closes the generator, and
    # yielding during GeneratorExit raises RuntimeError. "done" is emitted on the normal path.
    try:
        for _ in range(MAX_STEPS):
            msg = client.complete([_system(), *messages.to_api()], TOOLS)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                messages.add("assistant", msg.get("content"), tool_calls=tool_calls)
                yield "status", {"text": _status(tool_calls)}
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    result = dispatch(name, _args(tc))
                    messages.add("tool", json.dumps(result), tool_call_id=tc["id"], name=name)
                continue
            text = msg.get("content") or ""
            messages.add("assistant", text)
            for chunk in _chunks(text):
                yield "token", {"text": chunk}
            break
        else:
            yield "error", {"text": "Kiko couldn't finish that in time."}
    except LLMError as e:
        yield "error", {"text": _llm_error(e)}
    yield "done", {}


def _status(tool_calls) -> str:
    verbs = {"create": "Adding", "update": "Updating", "delete": "Removing", "list": "Checking"}
    name = tool_calls[0]["function"]["name"]
    verb = next((v for k, v in verbs.items() if name.startswith(k)), "Working on")
    thing = "your calendar" if name.endswith("event") or name == "list_events" else "your tasks"
    return f"{verb} {thing}…"


def _llm_error(e: LLMError) -> str:
    if str(e) == "no API key":
        return "Kiko is unavailable — set DEEPSEEK_API_KEY in your .env."
    return f"Kiko hit an error: {e}"
