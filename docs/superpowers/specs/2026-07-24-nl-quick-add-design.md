# F.R.I.D.A.Y. — Natural-Language Quick-Add Design (Spec K)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A, existing agent tool loop.

## 1. Context

Fast text entry without the full event/todo form: one box where the user types
"lunch with Kate tomorrow 12:30" or "todo buy cables" and FRIDAY parses it into
the right record. This is the typed sibling of a voice command — it reuses the
**existing agent tool loop** rather than building a new parser.

## 2. Goals / Non-goals

**Goals**
- A quick-add input (dashboard + calendar page) → `POST /api/quickadd {text}`.
- Server runs the text through the existing `run_text()` agent loop (same tools:
  `create_event`/`create_todo`), returns `{reply, actions}`.
- UI shows what was created and refreshes the relevant list.

**Non-goals**
- A bespoke NL date parser. The LLM already does this in the tool loop — reuse it,
  don't reimplement `date` grammar (YAGNI, no new dependency).
- Disambiguation dialogs. If ambiguous, the agent's `reply` asks; user re-submits.
- Bulk/multiline import.

## 3. Design

- `POST /api/quickadd` {`text`} → `run_text(text)` (the Spec B non-streaming agent
  helper) → return its `{reply, actions}`.
- The system prompt already covers create/edit/list; a light nudge ("prefer a
  single create action for quick-add") keeps it from over-asking.
- Frontend: small input + submit; on response, toast the `reply`, re-fetch
  `/api/events` or `/api/todos` per the `actions` returned.

Essentially zero new backend beyond one thin route wrapping `run_text`.

## 4. Testing

- Unit: `/api/quickadd` calls `run_text` (faked LLM) and returns its result.
- Unit: an event-shaped phrase yields a `create_event` action; a todo phrase
  yields `create_todo` (assert against faked tool dispatch, per existing patterns).

## 5. Risks

- **LLM latency** on every quick-add — acceptable; it's an explicit submit, and
  the same path already serves voice.
- **Wrong record type** — the `reply` tells the user what happened; delete is one
  click/undo (Spec S).
