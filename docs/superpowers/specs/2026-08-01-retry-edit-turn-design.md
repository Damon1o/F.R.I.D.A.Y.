# F.R.I.D.A.Y. — Retry / Edit Last Turn Design (Spec AD)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec A/B (agent loop, `messages` module), Spec AB (toasts).
**Estimate:** ~40 minutes.

## 1. Context

When a reply is wrong, cut short by a timeout, or answering a typo, the only recovery
is retyping the question. The conversation table already stores every turn with an
`id`, and `history()` already returns those ids to the client — everything needed to
rewind one turn is in place except a way to delete forward from a point.

Two actions, one mechanism:
- **Retry** — drop the last assistant turn, resend the same user text.
- **Edit** — drop the last assistant *and* user turn, put the user text back in the
  input for editing, send on submit.

## 2. Goals / Non-goals

**Goals**
- `DELETE /api/friday/history/<id>` removes that message and everything after it in
  the current thread.
- Hover controls on the last turn only: "Retry" and "Edit".
- Both reuse the existing `send()` path — no second streaming client.

**Non-goals**
- Branching conversations / alternate response trees. The old turn is gone.
- Editing arbitrary earlier turns. Last turn only; anything deeper is a new question.
- Regenerate-with-different-model or temperature knobs.
- Undo of the delete. `Esc`-proof confirmation is not warranted for one turn in a
  single-user app.

## 3. Design

**Server** — one route in `pages/friday/routes.py`:

```python
@friday_bp.route("/api/friday/history/<int:message_id>", methods=["DELETE"])
def truncate(message_id):
    """Drop this message and every later one in the open thread — the rewind
    behind retry and edit. Returns the id of the last surviving turn."""
    return jsonify({"last": messages.truncate_from(message_id)})
```

and one function in `pages/friday/messages.py`, alongside the existing `clear()` and
`delete()`:

```python
def truncate_from(message_id: int) -> int | None:
    """Delete message_id and everything after it in the current thread."""
    execute("DELETE FROM messages WHERE thread_id = %s AND id >= %s",
            (current_thread(), message_id))
    row = one("SELECT MAX(id) AS t FROM messages WHERE thread_id = %s", (current_thread(),))
    return row["t"] if row else None
```

Scoping the delete to `current_thread()` matters — an id from a stale open tab must
not reach into a thread the user has since switched away from.

Note the loop reads context via `messages.to_api(limit=CONTEXT_WINDOW)`, so once the
rows are gone the retried turn is built from exactly the pre-question state. Tool
calls and tool results carry `thread_id` on the same table, so they are truncated
together — no orphaned `tool_call_id` referencing a deleted assistant message, which
would break the next API call.

**Client** (`friday.js`) — bubbles already carry the message; add the id.
`render()`/`bubble()` set `el.dataset.id = m.id`. After each render, the last
assistant bubble gets a controls row:

```js
function lastTurnControls(el, userText, userId) {
  var bar = document.createElement('div');
  bar.className = 'friday-turn-actions';
  bar.appendChild(actionBtn('Retry', async function () {
    if (await truncate(el.dataset.id)) { dropBubblesFrom(el); send(userText); }
  }));
  bar.appendChild(actionBtn('Edit', async function () {
    if (await truncate(userId)) { dropBubblesFrom(el, 1); input.value = userText; input.focus(); }
  }));
  el.appendChild(bar);
}
```

`truncate(id)` is a `DELETE` fetch that toasts and returns `false` on failure — the
bubbles stay on screen if the server did not actually rewind, so the UI never claims
a delete that did not happen.

The controls are attached only to the final assistant bubble and removed when a new
turn starts (`send()` clears any `.friday-turn-actions` before appending). They are
visible on hover and on `:focus-within`, so they are keyboard-reachable rather than
hover-only.

Both actions are no-ops while `inflight` is set — retrying mid-stream is ambiguous.
Reuse the existing `inflight` guard from `window.fridayStop`.

**Voice** — a retried turn streams identically, so `voice-web.js` speaks it with no
change. The `is-stopped` class logic is untouched.

## 4. Testing

Add to `tests/test_friday.py`:

1. `truncate_from` deletes the target row and all later rows, leaves earlier rows and
   *other threads* untouched.
2. Truncating an assistant turn that had tool calls also removes its `tool` rows —
   assert `to_api()` afterwards contains no `tool_call_id` without a matching
   assistant message.
3. `DELETE /api/friday/history/<id>` returns `{"last": ...}` and 200; a nonexistent id
   is a no-op, not a 500.
4. Retry path end-to-end with a faked LLM: send, truncate, send the same text, assert
   exactly one user turn and one assistant turn remain.

## 5. Risks

- **Dangling tool rows** breaking the next model call — covered by test 2. This is the
  one that actually bites; the API rejects a `tool` message whose `tool_call_id` has
  no originating assistant message.
- **Two tabs open** — tab B's stale bubble ids point at deleted rows. The delete is a
  no-op and the reply recovery path (`recoverReply`) already resyncs from history.
- **Cost** — a retry is a full billed turn. Acceptable; it is an explicit click.

## 6. Skipped deliberately

Branching, editing older turns, a diff view of the two answers, confirmation dialogs.
