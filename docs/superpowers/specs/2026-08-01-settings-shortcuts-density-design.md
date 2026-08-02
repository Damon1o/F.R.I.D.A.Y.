# F.R.I.D.A.Y. — Settings: Shortcut List + Density Design (Spec AH)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec AA (keyboard shortcuts — supplies `window.SHORTCUTS`).
**Estimate:** ~30 minutes.

## 1. Context

Two small additions to the existing Settings page (`templates/settings.html`, already
the largest template at ~23 KB, with the theme toggle and integration keys):

1. **Shortcut reference.** Spec AA adds bindings nobody can discover. The table is
   already exported as `window.SHORTCUTS`; Settings renders it.
2. **Density toggle.** The layout is sized for comfortable reading. On a laptop the
   calendar week grid and the todo list both show noticeably fewer rows than they
   could. One attribute on `<html>`, scaling the spacing tokens.

## 2. Goals / Non-goals

**Goals**
- A read-only "Keyboard" section listing every shortcut, generated from the table.
- A Comfortable / Compact control that sets `data-density` on `<html>` and persists it
  the same way the theme does.
- Compact re-scales spacing and row heights only — never font size below the existing
  body size, and never tap targets below 44 px on coarse pointers.

**Non-goals**
- Rebindable shortcuts (Spec AA non-goal, restated).
- A third density tier, or per-page density.
- Font-size or zoom controls; the browser already has those and does them better.

## 3. Design

### Shortcut list

New section in `settings.html`, populated by a few lines at the bottom of
`shortcuts.js` (guarded by element presence, so it costs nothing on other pages):

```js
var host = document.getElementById('shortcut-list');
if (host) window.SHORTCUTS.forEach(function (s) {
  var row = document.createElement('div');
  row.className = 'shortcut-row';
  var keys = document.createElement('span');
  keys.className = 'label-mono';
  s.keys.split(' ').forEach(function (k) {
    var kbd = document.createElement('kbd');
    kbd.textContent = k;
    keys.appendChild(kbd);
  });
  var label = document.createElement('span');
  label.textContent = s.label;
  row.append(keys, label);
  host.appendChild(row);
});
```

Generated, not hand-written, so a binding added to the table cannot go undocumented.
`<kbd>` styling: existing `--surface-2` background, `--r-1` radius, mono type.

### Density

`theme.js` already reads a stored preference and stamps `<html>` before first paint —
that inline-early placement is what avoids a flash. Density follows the identical
path in the same file (two more lines, no new script):

```js
var d = localStorage.getItem('density') || 'comfortable';
document.documentElement.setAttribute('data-density', d);
```

Persistence matches whatever the theme toggle already does — if theme is stored
server-side in `settings` rather than `localStorage`, density uses the same store and
the same server round trip. Do not introduce a second mechanism.

**Tokens** (`tokens.css`) — compact overrides the spacing scale only:

```css
:root[data-density="compact"] {
  --s-1: 2px; --s-2: 4px; --s-3: 8px; --s-4: 12px; --s-5: 16px; --s-6: 24px;
  --row-h: 32px;
  --cal-hour-h: 44px;
}
```

The exact source values come from the existing scale in `tokens.css`; compact is
roughly 0.75× with sane rounding. Because component CSS already references tokens and
never hex/px literals (project rule), nothing else changes.

Two exceptions must be written explicitly, since the token scale would otherwise
shrink them:

```css
@media (pointer: coarse) {
  :root[data-density="compact"] { --tap-min: 44px; }
}
```

and the week view's hour rows: `calendar-week.js` positions chips with
`top = minutes + 'px'`, i.e. it assumes 1 px per minute (`nowMinutes()`, the
`.cal-now` line, and `scrollTop = nowMinutes() - 120` all encode it). Compact density
therefore **must not** change the week grid's pixel-per-minute scale, or every chip
lands in the wrong slot. Either leave `--cal-hour-h` at 60 px under compact, or make
`calendar-week.js` read the scale from a CSS variable — the former is one line and is
the recommended choice.

**Control markup** — matches the existing settings rows (label, description, control
on the right); a two-button segmented control, `aria-pressed` on the active one.

## 4. Testing

`tests/test_settings.py` (existing file):

1. `settings.html` contains `#shortcut-list` and the density control.
2. `data-density="compact"` block in `tokens.css` defines every `--s-*` token the
   default `:root` defines — a partially overridden scale gives inconsistent spacing.
3. Compact does **not** override `--cal-hour-h` away from 60 (guards the week-view
   pixel-per-minute assumption above). This is the one test worth having.

Manual: switch to compact, open the calendar week view, confirm an event at 14:30
still lands at 14:30, and reload to confirm no flash of comfortable spacing.

## 5. Risks

- **Week-view misalignment** — the pixel-per-minute coupling described above. Test 3
  and the one-line exception cover it; this is the only thing in this spec that can
  actually break a feature.
- **Flash of wrong density** on load if the attribute is stamped late. It rides in
  `theme.js`, which is already the non-deferred first script for exactly this reason.
- **Touch targets** under compact — the coarse-pointer floor above.

## 6. Skipped deliberately

Rebinding UI, more density tiers, per-page density, font scaling, a `?` cheat-sheet
overlay.
