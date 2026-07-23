# Kiko — Phase 2 (Assistant) Design

**Date:** 2026-07-22
**Status:** Approved (design), pending implementation
**App:** Kiko — personal voice-driven productivity web app (single user, localhost)
**Builds on:** `2026-07-21-phase1-core-design.md` (Phase 1 shipped, 22 tests green)

## 1. Overview

Phase 2 turns the inert right-column Kiko panel into a working chat that creates,
edits, deletes and reads events and todos from natural language. An LLM (DeepSeek)
drives a server-side tool-calling loop; the tools wrap the **existing** Phase 1 model
functions — no DB logic is duplicated.

**In scope:**
- DeepSeek chat client (`core/llm.py`), OpenAI-compatible `chat/completions`.
- Tool-calling loop that maps LLM tool calls to `create_event` / `update_event` /
  `delete_event` / `list_events` and the todo equivalents.
- Chat history persisted in SQLite (single implicit thread) so multi-turn edits work
  ("move that meeting to tomorrow"). A **New chat** control clears it.
- The always-on panel wired: input enabled, message list, streamed replies.

**Out of scope (later phases):** voice / whisper (Phase 3), scheduler / Discord (Phase 4),
multiple conversations, per-message undo, auth.

## 2. Decisions (locked in brainstorming)

| Question | Decision |
|----------|----------|
| Provider | **DeepSeek** (`deepseek-chat`), OpenAI-compatible, `DEEPSEEK_API_KEY` in `.env` |
| Mutations | **Act immediately** — Kiko runs the tool, reports what it did. No confirm step. |
| History | **Persist in SQLite** — single thread; a clear endpoint wipes it |
| Transport | **Single POST returns `text/event-stream`**: `status` frames during the tool loop, `token` frames for the final reply, then `done`. Never streams mid-tool-call. |

## 3. Data model

One new table (single-user, single implicit thread — no `conversations` table, YAGNI):

```sql
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    role         TEXT NOT NULL,        -- user | assistant | tool
    content      TEXT,                 -- text, or tool-result JSON for role=tool
    tool_calls   TEXT,                 -- JSON array when assistant requests tools
    tool_call_id TEXT,                 -- role=tool: which call it answers
    name         TEXT,                 -- role=tool: tool name
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Stored rows are enough to replay the exact OpenAI-shaped message list back to DeepSeek.

## 4. Components

```
pages/kiko/
  __init__.py
  tools.py       TOOLS (JSON schemas) + dispatch(name, args) -> result dict
  messages.py    add(), history(), clear(), to_api()  (thin sqlite via core.db)
  agent.py       run_turn(user_text, client) -> generator of SSE frames
  routes.py      POST /api/kiko/message, GET /api/kiko/history, POST /api/kiko/clear
core/llm.py      DeepSeekClient.complete(messages, tools) — stdlib urllib, no new deps
```

**Tools** (name → existing model fn):

| Tool | Wraps | Args |
|------|-------|------|
| `create_event` | `create_event` | title, start_at, end_at?, all_day?, location?, notes? |
| `update_event` | `update_event` | event_id, + any editable field |
| `delete_event` | `delete_event` | event_id |
| `list_events` | `list_events` | start?, end? |
| `create_todo` | `create_todo` | title, due_at?, notes? |
| `update_todo` | `update_todo` | todo_id, title?, due_at?, notes?, done? |
| `delete_todo` | `delete_todo` | todo_id |
| `list_todos` | `list_todos` | done? |

`dispatch` catches `ValidationError` and returns `{"error": ...}` as the tool result so
the LLM can self-correct rather than crashing the turn.

## 5. Data flow (one turn)

1. `POST /api/kiko/message {text}` → persist user message → respond `text/event-stream`.
2. `agent.run_turn`:
   a. Build message list = system prompt (current datetime injected) + stored history.
   b. Call DeepSeek (non-streaming) with tool schemas.
   c. Response has `tool_calls`? → emit `status` frame ("Scheduling…"), persist the
      assistant tool-call message, run each tool via `dispatch`, persist each tool
      result, loop to (b). Hard cap of 6 iterations guards runaway loops.
   d. No `tool_calls` → persist the final assistant text, emit it as `token` frames
      (server-paced chunks of the received message — the tool phase stays non-streamed,
      so nothing streams mid-tool-call), then `done`.
3. Any exception → `error` frame + `done`; user message stays, partial state is committed
   per tool (immediate-action model).

**SSE frame shapes** (`data:` is JSON):
- `event: status` `data: {"text": "Scheduling…"}`
- `event: token`  `data: {"text": "Added "}`
- `event: error`  `data: {"text": "Kiko is unavailable (no API key)."}`
- `event: done`   `data: {}`

## 6. Client (`static/js/kiko.js`, loaded globally in `base.html`)

Panel is on every page (server-rendered multi-page). On load, `kiko.js` fetches
`GET /api/kiko/history` and renders the thread. Submit POSTs the text and reads the
`text/event-stream` body via `fetch` + `ReadableStream`: append a "typing" bubble,
apply `status` text to it, append `token` chunks to the assistant bubble, finalize on
`done`. **New chat** button POSTs `/api/kiko/clear` and empties the list.

## 7. Config

```
DEEPSEEK_API_KEY   (required for live replies; absent → friendly error frame)
DEEPSEEK_BASE_URL  default https://api.deepseek.com
DEEPSEEK_MODEL     default deepseek-chat
```

Missing key is not a crash: the agent emits an `error` frame telling the user to set it.

## 8. Error handling

- No API key → `error` frame, no exception.
- DeepSeek HTTP / network error → caught, `error` frame with a short message.
- Tool `ValidationError` → returned to the LLM as a tool result (self-correct), not fatal.
- Tool-loop cap (6) → stop, emit whatever text exists or a "couldn't complete" note.

## 9. Testing

`tests/test_kiko.py`, LLM always mocked (a `FakeClient` returning scripted responses):

- **tools**: each `dispatch` name hits the right model fn; bad args → `{"error": …}`.
- **agent loop**: FakeClient scripts `[tool_call create_todo] → [final text]`; assert the
  todo exists, both assistant + tool rows persisted, frames are `status…token…done`.
- **no key**: agent emits a single `error` frame, no rows lost.
- **persistence**: `history()` round-trips; `clear()` empties.
- **endpoint smoke**: `POST /api/kiko/message` with a patched client returns an event
  stream ending in `done`; `GET /api/kiko/history` returns the thread; `clear` empties.

No live network in tests. `run_turn` takes the client as a parameter (default = real
`DeepSeekClient`) so tests inject the fake.

## 10. Done when

- Typing "add a dentist appointment Friday 3pm" creates the event and Kiko confirms.
- "what's on my schedule this week" lists events (read tool), no mutation.
- History survives navigation and restart; New chat clears it.
- No API key shows a friendly message, never a 500.
- All Phase 1 tests still green; new `test_kiko.py` green.
- No new pip dependency (stdlib `urllib`); no external CDN; icons via Lucide.
