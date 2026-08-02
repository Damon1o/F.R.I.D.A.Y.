# F.R.I.D.A.Y. — Loading Skeletons Design (Spec AF)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** nothing.
**Estimate:** ~40 minutes.

## 1. Context

Pages render their shell server-side, then fetch their data. Between those two
moments the cards are empty — the calendar grid has no chips, the todo list is a bare
container, the mail list is blank. On Vercel serverless with a cold function that gap
is long enough to read as "broken and empty" rather than "loading", which is the
exact confusion an empty-state message (Spec AG) would *also* produce. The two specs
must not collide: a skeleton means "wait", an empty state means "there is nothing".

## 2. Goals / Non-goals

**Goals**
- One CSS class, `.skeleton`, that turns any box into a shimmering placeholder.
- Each list-backed view renders placeholder rows before its first fetch resolves.
- Skeleton is replaced by real content *or* by the empty state — never left behind.
- `prefers-reduced-motion` drops the shimmer to a static tint.

**Non-goals**
- Per-component bespoke skeleton shapes matching exact final layouts. Generic bars
  at the right row height are enough.
- A skeleton for the assistant reply — the pending bubble and status text already
  cover it.
- Server-rendered skeletons in Jinja. They belong to the client fetch lifecycle.

## 3. Design

**CSS** (`app.css`, tokens only):

```css
.skeleton {
  background: linear-gradient(90deg,
    var(--surface-2) 25%, var(--surface-3) 37%, var(--surface-2) 63%);
  background-size: 400% 100%;
  border-radius: var(--r-2);
  animation: skeleton-sweep 1.4s ease infinite;
}
@keyframes skeleton-sweep { from { background-position: 100% 0 } to { background-position: 0 0 } }
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; background: var(--surface-2); }
}
```

If `--surface-3` does not exist in `tokens.css`, the gradient uses
`--surface-2`/`--surface-1` instead. No hex literals — the project rule holds.

**Usage** — a three-line helper per page module, not a shared component:

```js
function skeletonRows(host, n, h) {
  host.innerHTML = '';
  for (var i = 0; i < n; i++) {
    var el = document.createElement('div');
    el.className = 'skeleton';
    el.style.height = (h || 44) + 'px';
    el.style.margin = '0 0 8px';
    host.appendChild(el);
  }
}
```

Call sites:

- **Calendar month/week** — the grid itself is structural and renders instantly; only
  the chips are missing. Skeleton is *skipped* here: an empty grid with correct dates
  is not confusing. Deliberate exception; do not add one.
- **Todos** (`todos.js`) — 5 rows before `/api/todos`.
- **Notes** (`notes.js`) — 4 rows at 64 px.
- **Mail** (`pages/mail`) — 6 rows at 56 px.
- **Grades / SAT** — 3 rows before their fetch.
- **Dashboard widgets** (`widgets.js`) — one skeleton block per widget body.
- **Friday thread list** (`friday.html` `#thread-list`) — 4 rows at 36 px.

**Lifecycle rule** — the skeleton is written in the same function that starts the
fetch, and the render function always clears the host before writing. Both paths
(success with rows, success with zero rows) therefore overwrite it. A `catch` must
also clear it and toast (Spec AB) — a stuck shimmer after a failed fetch is worse
than a blank box, because it never resolves.

**Minimum-duration flicker** — skipped. If a warm response beats the paint, the
skeleton is never seen, which is the desired outcome. Do not add an artificial delay
to "avoid flashing".

## 4. Testing

`tests/test_skeletons.py`:

1. `.skeleton` exists in `app.css` and contains no hex literal (regex `#[0-9a-fA-F]{3,8}`)
   — enforces the project's token rule for the new rules specifically.
2. A `prefers-reduced-motion` block referencing `.skeleton` is present.

Manual: throttle to Slow 3G in devtools, load each listed page, confirm the shimmer
appears and is fully replaced.

## 5. Risks

- **Left behind on error** — covered by the lifecycle rule above; it is the only real
  failure mode and it must be handled at every call site, including `catch`.
- **Layout shift** when real rows are a different height than the placeholder. Match
  the heights listed above to the real row heights; a few pixels of shift is
  acceptable, a doubling is not.

## 6. Skipped deliberately

A `<Skeleton>` component abstraction, per-view bespoke shapes, minimum display
durations, calendar chip skeletons.
