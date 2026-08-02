# F.R.I.D.A.Y. — Keyboard Shortcuts Design (Spec AA)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec Z (command palette) for `Ctrl+K`; otherwise standalone.
**Estimate:** ~40 minutes.

## 1. Context

The app is single-user and used daily, which is exactly the profile that pays back
shortcuts. Two already exist and are undocumented: `Esc` stops a streaming reply
(`friday.js`), and the send button doubles as stop. Everything else is a click.

This spec adds a small, fixed set of bindings in one file, plus the discoverability
piece — a shortcuts list in Settings (see Spec AH).

## 2. Goals / Non-goals

**Goals**
- One module owns global bindings; page modules keep their own local ones.
- Bindings never fire while typing in an input, textarea, or `contenteditable`.
- A `g`-prefixed go-to chord (`g` then `c` → Calendar), Gmail-style.
- The list is data, so Settings can render it without duplicating it.

**Non-goals**
- User-configurable bindings. Single user, edit the array.
- A keybinding library (`mousetrap`, `hotkeys-js`). One `keydown` listener.
- Vim modes, multi-key sequences longer than two, chord timeouts beyond one.

## 3. Design

New file `static/js/shortcuts.js`, loaded in `base.html`. It exports the table so
Settings can read it:

```js
window.SHORTCUTS = [
  { keys: 'Ctrl K',  label: 'Open command palette' },   // handled by palette.js
  { keys: '/',       label: 'Focus search' },
  { keys: 'f',       label: 'Focus F.R.I.D.A.Y. input' },
  { keys: 'c',       label: 'New event (calendar page)' },
  { keys: 't',       label: 'Toggle theme' },
  { keys: 'Esc',     label: 'Stop the reply / close overlays' },
  { keys: 'g d',     label: 'Go to Dashboard' },
  { keys: 'g c',     label: 'Go to Calendar' },
  { keys: 'g t',     label: 'Go to Tasks' },
  { keys: 'g n',     label: 'Go to Notes' },
  { keys: 'g a',     label: 'Go to Assistant' },
  { keys: 'g m',     label: 'Go to Mail' },
  { keys: 'g s',     label: 'Go to Settings' },
];
```

**The guard** — the single most important line, since every miss types a letter into
a form the user is filling:

```js
function typing(e) {
  var t = e.target;
  return t.isContentEditable ||
         /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
}
```

**The listener**:

```js
var chord = null, chordTimer = null;

document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;   // palette.js owns Ctrl+K
  if (typing(e)) return;

  if (chord === 'g') {
    clearTimeout(chordTimer); chord = null;
    var dest = GO[e.key];
    if (dest) { e.preventDefault(); location.href = dest; }
    return;
  }
  if (e.key === 'g') { chord = 'g'; chordTimer = setTimeout(function () { chord = null; }, 1200); return; }

  var run = SINGLE[e.key];
  if (run) { e.preventDefault(); run(); }
});
```

`GO` maps a letter to a path (same literal paths as the palette). `SINGLE` maps a
letter to a function: focus `#search-input`, focus `#friday-input`, click
`#theme-toggle`, click `#cal-new` if present.

**`Esc`** stays where it is. `friday.js` already binds it for stopping a stream, and
`calendar-week.js` closes its context menu. Adding a third owner in `shortcuts.js`
would fight them; leave `Esc` distributed and just document it in the table.

**Page-local bindings** (`c` for new event) are gated by element presence — `SINGLE.c`
checks `document.getElementById('cal-new')` and no-ops elsewhere. No per-page
registration API until a second page needs one.

## 4. Testing

`tests/test_shortcuts.py`:

1. `shortcuts.js` is referenced in `base.html`.
2. Every `keys` entry in the table has a non-empty `label` (parse the JS file with a
   regex — the table is a literal, so this is cheap and catches a half-added row).
3. Every path in `GO` resolves to a real route (`app.url_map`) — this one *is* worth
   asserting, because a dead go-to chord is silent.

Manual: type `g` inside the Friday input and confirm the letter lands in the box and
does not navigate. That is the whole regression surface.

## 5. Risks

- **Firing while typing** — the guard above. Test it by hand in every text field the
  app has (search, Friday input, event title, note body, settings fields).
- **Chord left hanging** — the 1200 ms timeout clears it; a stale `g` would otherwise
  swallow the next keystroke.
- **Native shortcut shadowing** — single unmodified letters are free in browsers;
  `/` is Firefox quick-find, which `preventDefault()` suppresses.

## 6. Skipped deliberately

Configurability, a registration API, a cheat-sheet overlay bound to `?`. The Settings
list (Spec AH) covers discoverability at a fraction of the cost.
