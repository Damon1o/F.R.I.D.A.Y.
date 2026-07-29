"""Chat history persistence — conversations are threads in the `messages` table.

The open thread is a single pointer in `settings` (single-user app), so "new chat"
starts thread N+1 and every earlier conversation stays readable.
"""
import json

from core.db import execute, query


def current_thread() -> int:
    """Open thread. Falls back to the newest stored thread when no pointer exists."""
    row = query("SELECT value FROM settings WHERE key = 'friday_thread'", one=True)
    if row:
        return int(row["value"])
    row = query("SELECT COALESCE(MAX(thread_id), 1) AS t FROM messages", one=True)
    return int(row["t"])


def set_thread(thread_id: int) -> int:
    execute(
        "INSERT INTO settings (key, value) VALUES ('friday_thread', %s) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (str(thread_id),),
    )
    return thread_id


def new_thread() -> int:
    row = query("SELECT COALESCE(MAX(thread_id), 0) AS t FROM messages", one=True)
    return set_thread(int(row["t"]) + 1)


def title(thread_id: int) -> str | None:
    """Stored name of a conversation, or None while it is still untitled.

    Names live in `settings` under `thread_title:N` — no threads table needed, and
    an untitled thread just falls back to its first user message.
    """
    row = query("SELECT value FROM settings WHERE key = %s",
                (f"thread_title:{thread_id}",), one=True)
    return row["value"] if row else None


def set_title(thread_id: int, text: str) -> str:
    execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (f"thread_title:{thread_id}", text),
    )
    return text


def threads() -> list[dict]:
    """One row per conversation, newest first. Stored name wins; else first user message."""
    rows = query(
        "SELECT DISTINCT ON (thread_id) thread_id, content, created_at FROM messages "
        "WHERE role = 'user' AND content <> '' ORDER BY thread_id DESC, id"
    )
    names = {r["key"]: r["value"] for r in
             query("SELECT key, value FROM settings WHERE key LIKE %s", ("thread_title:%",))}
    return [{"id": r["thread_id"],
             "title": names.get(f"thread_title:{r['thread_id']}") or r["content"],
             "created_at": r["created_at"]}
            for r in rows]


def add(role, content=None, *, tool_calls=None, tool_call_id=None, name=None) -> None:
    execute(
        "INSERT INTO messages (role, content, tool_calls, tool_call_id, name, thread_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (role, content, json.dumps(tool_calls) if tool_calls else None, tool_call_id, name,
         current_thread()),
    )


def history(limit: int | None = None, before_id: int | None = None,
            thread_id: int | None = None) -> list[dict]:
    """Raw stored rows of one thread, oldest first (the UI filters to displayable text).

    `limit` takes the newest N rows; `before_id` pages backwards from there, so the
    panel opens on the tail of a long thread instead of replaying thousands of rows.
    """
    thread = current_thread() if thread_id is None else thread_id
    if limit is None and before_id is None:
        return [dict(r) for r in
                query("SELECT * FROM messages WHERE thread_id = %s ORDER BY id", (thread,))]
    sql = "SELECT * FROM messages WHERE thread_id = %s"
    params: list = [thread]
    if before_id is not None:
        sql += " AND id < %s"
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
    rows = list(query("SELECT * FROM messages WHERE thread_id = %s ORDER BY id",
                      (current_thread(),)))
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
    """Delete the open conversation. Other threads are untouched."""
    execute("DELETE FROM messages WHERE thread_id = %s", (current_thread(),))


def delete(thread_id: int) -> int:
    """Drop a conversation and its name. Returns the thread left open — deleting the
    open one falls back to the newest surviving thread."""
    execute("DELETE FROM messages WHERE thread_id = %s", (thread_id,))
    execute("DELETE FROM settings WHERE key = %s", (f"thread_title:{thread_id}",))
    if current_thread() != thread_id:
        return current_thread()
    row = query("SELECT COALESCE(MAX(thread_id), 1) AS t FROM messages", one=True)
    return set_thread(int(row["t"]))
