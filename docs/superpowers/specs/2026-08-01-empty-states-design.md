# F.R.I.D.A.Y. — Empty States Design (Spec AG)

**Date:** 2026-08-01
**Status:** Draft (design).
**Depends on:** Spec AF (skeletons) — the two must not be confusable.
**Estimate:** ~40 minutes.

## 1. Context

`app.css` has exactly one empty-state rule today:

```css
.scroll-list .empty { padding: var(--s-4); color: var(--on-surface-faint); }
```

…which styles whatever bare string a module happens to write, and most modules write
nothing at all. A first-run or cleared-out view is therefore a blank card that looks
identical to a broken one. Every empty view is also the single best place to put the
action that fills it — a blank card wastes that.

## 2. Goals / Non-goals

**Goals**
- One markup pattern: Lucide icon, one-line headline, one-line hint, one action button.
- Every list-backed view has one, with copy written for that view.
- The empty state renders only after a *successful* fetch that returned zero rows —
  never on error (that is a toast, Spec AB) and never while loading (that is a
  skeleton, Spec AF).

**Non-goals**
- Illustrations or art. Monochrome design system; a 24 px Lucide glyph is the ceiling.
- Per-filter empty states ("no results for that search" vs "no todos") beyond the two
  obvious cases listed below.
- Onboarding tours, dismissible tips, first-run checklists.

## 3. Design

**Helper** — one function in a shared place. `toast.js` is already loaded on every
page ahead of the page modules (Spec AB), so it hosts this too rather than adding a
sixth script tag:

```js
window.emptyState = function (host, opts) {
  host.innerHTML = '';
  var el = document.createElement('div');
  el.className = 'empty-state';
  el.innerHTML =
    '<img src="/static/vendor/lucide/' + opts.icon + '.svg" alt="" width="24" height="24">' +
    '<p class="empty-title"></p><p class="empty-hint faint"></p>';
  el.querySelector('.empty-title').textContent = opts.title;
  el.querySelector('.empty-hint').textContent = opts.hint;
  if (opts.action) {
    var b = document.createElement('button');
    b.className = 'btn-primary';
    b.textContent = opts.action;
    b.addEventListener('click', opts.onAction);
    el.appendChild(b);
  }
  host.appendChild(el);
};
```

Every icon named below must exist in `static/vendor/lucide/` — add any missing one to
the pinned vendor set rather than fetching it.

**Copy** — the actual deliverable of this spec; the code is trivial:

| View | Icon | Headline | Hint | Action |
|---|---|---|---|---|
| Todos | `circle-check-big` | Nothing to do | Add a task, or ask F.R.I.D.A.Y. to. | New task |
| Todos (filtered) | `filter` | No tasks match | Clear the filter to see everything. | Clear filter |
| Notes | `file-text` | No notes yet | Notes you write or dictate land here. | New note |
| Calendar day/week | `calendar` | Nothing scheduled | Click any slot to add something. | — |
| Mail | `mail` | Inbox is clear | New mail shows up here. | — |
| Search results | `search` | No matches | Try a shorter or different word. | — |
| Friday threads | `message-square` | No past conversations | This is your first one. | — |
| Grades | `graduation-cap` | No grades loaded | Connect Infinite Campus in Settings. | Open Settings |
| SAT | `book-open-check` | No practice yet | Start a set to see your progress. | Start a set |

Copy rules used above: state the fact, not the absence ("Inbox is clear", not "No
emails found"); the hint says what *will* put something here; no exclamation marks;
no "Oops".

**CSS** (`app.css`, tokens only): `.empty-state` centres its children in a column,
`padding: var(--s-6) var(--s-4)`, `gap: var(--s-2)`, icon at `opacity: .5`.
`.empty-title` uses the normal body weight; `.empty-hint` reuses the existing `.faint`
colour. The existing `.scroll-list .empty` rule stays for any string-only call site
that has not migrated.

**Ordering rule** (restating AF, because getting this wrong is the whole failure mode):

```
render(rows):
  host.innerHTML = ''          // clears skeleton or previous empty state
  if rows.length: draw rows
  else: emptyState(host, …)
catch: host.innerHTML = ''; toast(…, {error:true})   // never an empty state
```

## 4. Testing

`tests/test_empty_states.py`:

1. Every icon named in the table above exists at
   `static/vendor/lucide/<name>.svg`. This is the test that actually catches
   something — a missing vendor asset is a broken image inside the state meant to
   reassure the user.
2. `.empty-state` rules in `app.css` contain no hex literals.

Manual: with an empty database, load each view and confirm headline, hint, and action.

## 5. Risks

- **Shown on error** — the ordering rule above; the `catch` clears without drawing.
- **Copy drift** between this table and the code. The table is the source; when a
  string changes, change it here too. No test enforces it — not worth the fixture.

## 6. Skipped deliberately

Illustrations, animation, per-filter variants beyond todos, onboarding, dismissible
hints, i18n.
