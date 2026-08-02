# F.R.I.D.A.Y. — Optimistic UI Design (Spec AC)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec AB (toasts — rollback needs a way to say so), Spec C (calendar),
Spec W (week view).
**Estimate:** ~1 hour.

## 1. Context

Every calendar and todo write is round-trip-blocking. `calendar-week.js` ends a drag
with `window.CAL.reload()` — the chip snaps back to its original slot, then the
server responds, then the whole grid re-renders and the chip appears in its new
place. On a serverless cold start that is a visible half-second of "did that work?".
Same for creating an event (modal closes, grid blank, grid returns) and checking off
a todo.

The fix is to render the intended state immediately and reconcile after. The
existing `reload()` already *is* the reconciliation step — it just needs to stop
being the only feedback.

## 2. Goals / Non-goals

**Goals**
- Drag/resize in the week view keeps the chip where the user dropped it, and only
  moves back if the server rejects the write.
- Create/edit/delete apply to the local view before the fetch resolves.
- Todo checkbox toggles instantly.
- Any failure rolls back *and* toasts, so a reverted change is never silent.

**Non-goals**
- A client-side store / state layer. The DOM is the state; that is the whole point of
  the server-rendered design.
- Offline queueing and replay. Offline writes fail and roll back (Spec AB toasts it).
- Optimistic assistant replies, mail sends, or anything with a side effect outside
  this app. Sending mail optimistically is a lie with consequences.

## 3. Design

The pattern, applied identically at each site — *mutate, fetch, reconcile or revert*:

```js
async function commit(apply, revert, request) {
  apply();
  try {
    var res = await request();
    if (!res.ok) throw new Error(res.status);
  } catch (e) {
    revert();
    window.toast('Could not save — reverted.', { error: true });
    return false;
  }
  return true;
}
```

This lives in `calendar.js` and is exposed on the existing `window.CAL` object, which
`calendar-week.js` already talks to (`window.CAL.reload`, `.openModal`, `.setLabel`).
No new module.

**Week-view drag** (`calendar-week.js`, `pointerup` path). Today:

```js
if (!d.moved) { window.CAL.openModal(d.ev); return; }
// …PATCH…
window.CAL.reload();                            // re-render from the server either way
```

Becomes: the chip is already at the dropped position from the drag preview, so
`apply` is a no-op beyond keeping it there; `revert` restores the saved
`{start_at, end_at}` and re-lays out that one chip; success calls `reload()` as it
does now, which is now invisible because the DOM already matches. The
`pointercancel` handler's unconditional `reload()` stays — a cancelled drag has no
intended state to keep.

**Create** — on modal submit, close the modal and insert a provisional chip built
from the form values with `data-provisional="1"` and a dimmed style. On success,
`reload()` replaces it with the real one (which now carries an id). On failure,
remove the provisional chip and toast.

**Delete** — remove the chip, then `DELETE`. On failure, `reload()` brings it back
and toasts. `calendar.js:135` currently ignores `res.ok` entirely; this fixes that as
a side effect.

**Todos** (`todos.js`) — toggle the checkbox and the row's done class before the
`PATCH`; revert both on failure. Smallest instance of the same pattern.

**Reconciliation rule** — success always still calls `reload()`. It is one cheap GET
and it guarantees the client never drifts from the server (recurring expansions,
server-side clamping, another device's edits). Optimism buys the *perception*; the
reload keeps the *truth*. Do not skip it to save a request.

## 4. Testing

Server-side contract tests in `tests/test_calendar.py` (existing file):

1. `PATCH /api/events/<id>` with an out-of-range time returns a non-2xx — the client
   rollback path is only reachable if the server actually rejects bad writes.
2. `DELETE /api/events/<id>` on a missing id returns 404, not 200. Optimistic delete
   must be able to tell "gone already" from "failed".

Manual, and this is the real test: throttle the dev server (or stop it), drag an
event, confirm the chip returns to its original slot and a toast explains why.

## 5. Risks

- **Divergence** if the reconciling `reload()` is skipped anywhere. It is not; the
  spec makes it unconditional on success.
- **Double-apply** — a fast second drag before the first resolves. The chip's own
  `data-event` is updated by `apply`, so the second drag starts from the optimistic
  values; if the first write then fails, the revert restores stale coordinates. Given
  a single user on one screen, accept it — the trailing `reload()` corrects within a
  second either way.
- **Provisional chip surviving a failed create** — the removal is in the `catch`, and
  the trailing `reload()` on the success path clears it regardless.

## 6. Skipped deliberately

A state store, mutation queues, request de-duplication, offline replay, optimistic
mail/assistant actions.
