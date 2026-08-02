# F.R.I.D.A.Y. — Tool-Call Transparency Design (Spec AE)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec A/B (agent loop, SSE frames).
**Estimate:** ~1 hour.

## 1. Context

The agent already tells the client when it is working: `agent.py` yields
`("status", {"text": _status(tool_calls)})` before running tools, and `friday.js`
renders that string into the pending bubble — where the first token immediately
overwrites it (`if (!streamed) pending.textContent = payload.text`).

So the information exists and is thrown away. After a reply lands, there is no way to
tell whether "the game is at 7pm" came from a web search, from the calendar, or from
the model's imagination. That matters most for exactly the tools that can be wrong:
`search_web`, `read_mail`, `get_weather`.

## 2. Goals / Non-goals

**Goals**
- A compact, collapsed line under each assistant reply: `Used 2 tools`, expanding to
  `search_web — "eagles game time"` and `list_events — Aug 1–2`.
- Driven by a new `tool` SSE frame carrying `{name, summary}` — no payloads.
- Survives a reload for the current session's turns; absent for older history is
  acceptable (see risks).

**Non-goals**
- Showing raw tool arguments or raw results. Results are untrusted text (search
  snippets, mail bodies); rendering them as UI invites exactly the injection surface
  Spec H's prompt line guards against. Summaries are built server-side from the tool
  *name* and a short, sanitised argument echo.
- A debugging/trace panel, token counts, latency timings.
- Retroactively backfilling tool metadata for existing rows.

## 3. Design

**Server** (`pages/friday/agent.py`). The loop already has `tool_calls` in hand where
it yields the status frame. Add one frame per call, immediately after:

```python
yield "status", {"text": _status(tool_calls)}
for call in tool_calls:
    yield "tool", {"name": call.function.name, "summary": _summary(call)}
```

`_summary(call)` is deliberately dumb and lives next to `_status`:

```python
def _summary(call) -> str:
    """One short, safe line per call. Arguments only — never results, which are
    attacker-controllable text."""
    try:
        args = json.loads(call.function.arguments or "{}")
    except ValueError:
        return ""
    for key in ("query", "title", "text", "location", "to"):
        if args.get(key):
            return str(args[key])[:80]
    return ""
```

Truncating at 80 characters keeps a hostile-length argument from stretching the
layout; the client sets the text with `textContent`, so markup in an argument is
inert.

**Persistence.** The `messages` table already stores `tool_calls` on assistant rows
(`messages.add(..., tool_calls=...)`). `to_api()` reads them for the model; the
`/api/friday/history` route currently projects only `{id, role, content}`. Extend the
projection to include a `tools` list derived from the stored `tool_calls`, using the
same `_summary`. That gets reload-persistence for free — no new column, no migration.

**Client** (`friday.js`):

- `send()` collects `tool` frames into a local array.
- On `done` (or in the `finally`), if the array is non-empty, append a `<details>`
  under the reply bubble:

```js
function toolNote(el, calls) {
  var d = document.createElement('details');
  d.className = 'friday-tools';
  var s = document.createElement('summary');
  s.textContent = 'Used ' + calls.length + (calls.length === 1 ? ' tool' : ' tools');
  d.appendChild(s);
  calls.forEach(function (c) {
    var p = document.createElement('p');
    p.textContent = c.summary ? c.name + ' — ' + c.summary : c.name;
    d.appendChild(p);
  });
  el.appendChild(d);
}
```

`<details>`/`<summary>` is native disclosure — keyboard-accessible, no JS toggle, no
ARIA to hand-write. `render()` calls the same function from the history payload.

**CSS** (`app.css`): `.friday-tools` uses `--on-surface-faint`, mono label type, and
`font-size: var(--fs-xs)`. The marker is replaced with a Lucide `chevron-right` that
rotates on `[open]`. No new tokens.

## 4. Testing

Add to `tests/test_friday.py`:

1. A faked LLM that calls `search_web` produces a `tool` frame with
   `{"name": "search_web", "summary": "<query>"}` in the SSE stream.
2. `_summary` truncates at 80 characters and returns `""` for unparseable arguments
   rather than raising.
3. `/api/friday/history` includes `tools` for a stored assistant row that had tool
   calls, and omits/empties it for a plain reply.
4. A tool *result* string never appears in any frame — assert a canned result
   containing a sentinel is absent from the serialised stream. This is the security
   test, not a nicety.

## 5. Risks

- **Injection via arguments** — arguments are model-generated, not attacker-generated,
  but a poisoned search snippet could influence a *later* argument. `textContent` plus
  the 80-character cap bounds the damage to a weird-looking line.
- **Noise** — a turn with six tool calls shows a six-line disclosure. Collapsed by
  default, so the cost is one extra line of chrome.
- **Old history** has `tool_calls` stored already, so the backfill is automatic; rows
  from before that column existed simply render no note.

## 6. Skipped deliberately

Result previews, timings, token counts, a trace/debug view, per-tool icons.
