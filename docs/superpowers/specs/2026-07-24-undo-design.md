# F.R.I.D.A.Y. — Undo Design (Spec S)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A. **Related:** Spec B/voice, Spec K (quick-add) — the
mutations most likely to be wrong.

## 1. Context

Voice and agent mutations are one-shot and irreversible: a misheard "delete the
meeting" is gone. Add a single-level **undo** for the last destructive/mutating
action, surfaced in the UI and callable by voice ("undo that").

## 2. Goals / Non-goals

**Goals**
- Capture the inverse of the last mutation (create/update/delete of event/todo/note).
- `POST /api/undo` replays the inverse; an "Undo" affordance after an action.
- `undo_last` agent tool so "undo that" works by voice.

**Non-goals**
- Multi-level undo history / redo stack. One level covers the "oops" case (YAGNI).
- Undo for external side effects (sent email, played music, smart-home) — those
  aren't reversible/appropriate; undo is data-only.
- A full event-sourcing/audit system.

## 3. Design

- An `undo_log` holding the most recent reversible action as an inverse op:
  `{op: 'delete'|'restore'|'update', table, row_id, payload}`.
  - a create → inverse is delete(id)
  - a delete → inverse is re-insert the captured full row
  - an update → inverse is the prior field values
- The model layer records the inverse whenever it mutates (a thin wrapper/helper
  around the existing `create/update/delete` in calendar/todos/notes models), keeping
  only the **latest** (single-level: overwrite each time).
- `POST /api/undo` applies the stored inverse, then clears it. `undo_last` tool
  calls the same.
- UI: after a mutating action returns, show a transient "Undo" button hitting
  `/api/undo`.

Single-user, single-level → one `undo_log` row, no per-session complexity.

## 4. Data

```sql
CREATE TABLE undo_log (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- one row
  op TEXT NOT NULL, target_table TEXT NOT NULL,
  row_id INTEGER, payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 5. Testing

- Unit: create→undo removes it; delete→undo restores the exact row (incl. id-less
  re-insert semantics); update→undo restores prior fields.
- Unit: only the latest action is undoable (second mutation overwrites the log).
- Unit: `undo_last` tool + `/api/undo` apply the inverse and clear the log.

## 6. Risks

- **Restore vs id reuse** — a restored deleted row may get a new id; anything that
  referenced the old id (rare, single-user) won't reconnect. Acceptable; document.
- **Concurrency** — negligible at single-user; last-writer-wins on the one row.
