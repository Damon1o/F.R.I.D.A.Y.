"""Thin DeepSeek chat client (OpenAI-compatible). Stdlib urllib, no new deps.

Non-streaming only: the agent runs the tool-call loop turn-by-turn, then paces the
final text to the client itself, so real token streaming from DeepSeek isn't needed.
"""
import json
import urllib.error
import urllib.request

from flask import current_app


class LLMError(RuntimeError):
    """Any failure reaching or parsing the DeepSeek response."""


class DeepSeekClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        cfg = current_app.config
        self.api_key = api_key if api_key is not None else cfg["DEEPSEEK_API_KEY"]
        self.base_url = (base_url or cfg["DEEPSEEK_BASE_URL"]).rstrip("/")
        self.model = model or cfg["DEEPSEEK_MODEL"]

    def complete(self, messages, tools=None) -> dict:
        """Return the assistant message dict: {role, content, tool_calls?}."""
        if not self.api_key:
            raise LLMError("no API key")
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(str(getattr(e, "reason", e)))
        except (ValueError, KeyError) as e:
            raise LLMError(f"bad response: {e}")
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError):
            raise LLMError("no choices in response")
