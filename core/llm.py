"""Thin DeepSeek chat client (OpenAI-compatible). Stdlib urllib, no new deps.

`complete` blocks for the whole reply; `stream` yields content deltas as they arrive
and returns the same assembled message dict, so the agent's tool loop is unchanged.
"""
import json
import urllib.error
import urllib.request

from flask import current_app


class LLMError(RuntimeError):
    """Any failure reaching or parsing the DeepSeek response."""


def _http_detail(e: "urllib.error.HTTPError") -> str:
    """Pull the provider's error message out of an HTTPError body if we can."""
    try:
        payload = json.loads(e.read().decode("utf-8"))
        msg = payload.get("error", {}).get("message")
        if msg:
            return f"{e.code} {msg}"
    except Exception:
        pass
    return f"{e.code} {e.reason}"


class DeepSeekClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        cfg = current_app.config
        self.api_key = api_key if api_key is not None else cfg["DEEPSEEK_API_KEY"]
        self.base_url = (base_url or cfg["DEEPSEEK_BASE_URL"]).rstrip("/")
        self.model = model or cfg["DEEPSEEK_MODEL"]

    def _request(self, messages, tools, stream):
        if not self.api_key:
            raise LLMError("no API key")
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        if stream:
            body["stream"] = True
        return urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

    def complete(self, messages, tools=None) -> dict:
        """Return the assistant message dict: {role, content, tool_calls?}."""
        req = self._request(messages, tools, stream=False)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # The response body carries the provider's real reason (e.g. bad model);
            # e.reason alone is just "Bad Request". Surface the body when present.
            raise LLMError(_http_detail(e))
        except urllib.error.URLError as e:
            raise LLMError(str(getattr(e, "reason", e)))
        except (ValueError, KeyError) as e:
            raise LLMError(f"bad response: {e}")
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError):
            raise LLMError("no choices in response")

    def stream(self, messages, tools=None):
        """Yield content deltas as they arrive; return the assembled message dict.

        Tool-call deltas arrive split across frames (name in one, arguments in pieces),
        so they're accumulated by index and handed back whole like `complete` does.
        """
        req = self._request(messages, tools, stream=True)
        msg = {"role": "assistant", "content": ""}
        calls: dict[int, dict] = {}
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue          # blank keep-alive lines and SSE comments
                    line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    delta = json.loads(line)["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        msg["content"] += delta["content"]
                        yield delta["content"]
                    for tc in delta.get("tool_calls") or []:
                        acc = calls.setdefault(tc.get("index", 0), {
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                        acc["id"] += tc.get("id") or ""
                        fn = tc.get("function") or {}
                        acc["function"]["name"] += fn.get("name") or ""
                        acc["function"]["arguments"] += fn.get("arguments") or ""
        except urllib.error.HTTPError as e:
            raise LLMError(_http_detail(e))
        except urllib.error.URLError as e:
            raise LLMError(str(getattr(e, "reason", e)))
        except (ValueError, KeyError, IndexError) as e:
            raise LLMError(f"bad response: {e}")
        if calls:
            msg["tool_calls"] = [calls[i] for i in sorted(calls)]
        return msg
