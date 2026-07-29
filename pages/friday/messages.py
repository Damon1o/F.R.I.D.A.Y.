"""Chat history persistence — one implicit thread in the `messages` table."""
import json

from core.db import execute, query


def add(role, content=None, *, tool_calls=None, tool_call_id=None, name=None) -> None:
    execute(
        "INSERT INTO messages (role, content, tool_calls, tool_call_id, name) "
        "VALUES (%s, %s, %s, %s, %s)",
        (role, content, json.dumps(tool_calls) if tool_calls else None, tool_call_id, name),
    )


def history(limit: int | None = None, before_id: int | None = None) -> list[dict]:
    """Raw stored rows, oldest first (for the UI; it filters to displayable text).

    `limit` takes the newest N rows; `before_id` pages backwards from there, so the
    panel opens on the tail of a long thread instead of replaying thousands of rows.
    """
    if limit is None and before_id is None:
        return [dict(r) for r in query("SELECT * FROM messages ORDER BY id")]
    sql = "SELECT * FROM messages"
    params: list = []
    if before_id is not None:
        sql += " WHERE id < %s"
        params.append(before_id)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit or 50)
    return [dict(r) for r in reversed(list(query(sql, tuple(params))))]


def to_api(limit=None) -> list[dict]:
    """Rebuild the OpenAI-shaped message list for replay to DeepSeek.

    Spec P — `limit` bounds the voice/chat context to the last N stored rows so the
    prompt stays small on long threads. The window is snapped forward to the first
    `user` turn so the replayed sequence is always valid (no orphan tool messages).
    """
    rows = list(query("SELECT * FROM messages ORDER BY id"))
    if limit:
        rows = rows[-limit:]
        for i, r in enumerate(rows):
            if r["role"] == "user":
                rows = rows[i:]
                break
    out = []
    for r in rows:
        if r["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": r["tool_call_id"],
                        "name": r["name"], "content": r["content"] or ""})
        elif r["role"] == "assistant" and r["tool_calls"]:
            out.append({"role": "assistant", "content": r["content"] or "",
                        "tool_calls": json.loads(r["tool_calls"])})
        else:
            out.append({"role": r["role"], "content": r["content"] or ""})
    return out


def clear() -> None:
    execute("DELETE FROM messages")
