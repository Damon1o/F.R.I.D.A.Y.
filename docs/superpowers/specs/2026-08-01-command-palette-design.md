# F.R.I.D.A.Y. — Command Palette Design (Spec Z)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec Q (unified search, `/api/search`), Spec AA (keyboard shortcuts) —
soft dependency; the palette works standalone, AA just adds more ways to reach it.
**Estimate:** ~1 hour.

## 1. Context

Every navigation today is a mouse trip to the rail, and finding a specific event or
note means going to its page first. The topbar already has a live search field that
queries `/api/search` and drops results below it. A palette is that same field,
promoted to a modal on `Ctrl+K`, with the app's pages mixed into the result set as
commands.

This is deliberately *not* a new search backend. `/api/search` already returns
cross-entity hits; the palette adds a client-side list of static destinations and
merges the two.

## 2. Goals / Non-goals

**Goals**
- `Ctrl+K` / `Cmd+K` anywhere opens a centred modal with one input.
- Empty query lists commands (the nav destinations + a few actions).
- Typing filters commands *and* queries `/api/search` (debounced) for events, todos,
  notes, mail.
- `↑`/`↓` move, `Enter` runs, `Esc` closes. Full keyboard round trip.

**Non-goals**
- Fuzzy-match scoring library. Substring match, case-insensitive, in that order:
  prefix hits before contains hits. No `fuse.js`.
- Recent/frecency ranking, history, pinned commands.
- Nested command modes ("> " prefixes, palette-within-palette).
- Replacing the topbar search. Both stay; they share the fetch helper.

## 3. Design

New file `static/js/palette.js`, loaded from `base.html` (after `search.js`, so it
can reuse its fetch helper if one is exported; otherwise it duplicates six lines —
cheaper than refactoring `search.js`).

**Markup** — appended once to `base.html`, before the script tags, hidden by default:

```html
<div class="palette-scrim" id="palette" hidden>
  <div class="palette glass" role="dialog" aria-modal="true" aria-label="Command palette">
    <input id="palette-input" type="text" autocomplete="off" spellcheck="false"
           placeholder="Jump to a page, event, task, note…" aria-controls="palette-list">
    <div class="palette-list" id="palette-list" role="listbox"></div>
  </div>
</div>
```

**Commands** — a literal array in `palette.js`; the URLs come from the same routes
the rail uses, hardcoded because `url_for` is server-side and the palette is not
rendered per page:

```js
var COMMANDS = [
  { label: 'Dashboard',  icon: 'layout-dashboard',  url: '/' },
  { label: 'Calendar',   icon: 'calendar',          url: '/calendar' },
  { label: 'Tasks',      icon: 'circle-check-big',  url: '/todos' },
  { label: 'Notes',      icon: 'file-text',         url: '/notes' },
  { label: 'Assistant',  icon: 'message-square',    url: '/friday' },
  { label: 'Music',      icon: 'music',             url: '/music' },
  { label: 'Mail',       icon: 'mail',              url: '/mail' },
  { label: 'Grades',     icon: 'graduation-cap',    url: '/grades' },
  { label: 'SAT Prep',   icon: 'book-open-check',   url: '/sat' },
  { label: 'Settings',   icon: 'settings',          url: '/settings' },
  { label: 'New event',  icon: 'plus',   run: function () { location.href = '/calendar#new'; } },
  { label: 'Toggle theme', icon: 'sun',  run: function () { document.getElementById('theme-toggle').click(); } },
];
```

Icons are rendered by cloning the existing inlined Lucide sprite usage — the palette
uses `<img src="/static/vendor/lucide/<name>.svg">` since it builds markup in JS and
has no access to the Jinja `icon()` macro. Any icon it names must already exist in
`static/vendor/lucide/`; `plus` is added if missing.

**Search results** — on input, debounce 150 ms, `fetch('/api/search?q=' + q)`, render
under a "Results" group heading. Commands group renders first, always.

**Selection state** — one `activeIndex` integer over the flattened row list.
`↑`/`↓` clamp (no wrap — wrap loses the user). `Enter` calls `row.run()` or sets
`location.href`. Clicking a row does the same.

**Open/close** — `keydown` on `document`: `(e.ctrlKey || e.metaKey) && e.key === 'k'`
→ `preventDefault()`, show, focus, select-all. `Esc` closes. Clicking the scrim
closes. On close, the input is cleared so the next open starts fresh.

**Focus** — the palette stores `document.activeElement` on open and restores it on
close. Focus is not trapped beyond that; the modal has exactly one focusable input,
so `Tab` leaving it is closed off by returning focus to the input on `blur` while
open.

**CSS** (`app.css`, tokens only): scrim `background: var(--scrim)`; panel uses the
existing `.glass` surface, `max-width: 34rem`, centred at `top: 18vh`. Active row
uses the existing `.is-active` treatment from the nav. No new tokens.

## 4. Testing

`tests/test_palette.py` (server-side markup contract, matching the week-view test
pattern):

1. `base.html` renders `#palette` with the `hidden` attribute on any page.
2. `palette.js` is in the script list.
3. `/api/search?q=` returns the existing shape the palette expects (`title`, `url`,
   `kind`) — guards against a search refactor silently breaking the palette.

Manual: `Ctrl+K` on each page, arrow to a result, `Enter` navigates, `Esc` restores
focus to where it was.

## 5. Risks

- **Shortcut collision** — `Ctrl+K` is Chrome's address-bar search shortcut only when
  focus is in the omnibox; in-page it is free. `preventDefault()` covers the rest.
- **`/api/search` latency** — the commands list renders immediately and results append
  when they arrive; the palette is never blank while waiting.
- **Hardcoded URLs drift** if a blueprint route is renamed. The test asserting the nav
  and the palette agree is skipped deliberately (over-engineering); a broken link is a
  404, not a crash.

## 6. Skipped deliberately

Fuzzy scoring, command history, per-entity actions inside results (edit/delete from
the palette), a plugin registry for other modules to add commands. Add the registry
only when a second module actually wants to register something.
