# Calendar week view — design

Date: 2026-08-01
Status: implemented

## Problem

`/calendar` renders a month grid only. A day cell shows event titles stacked
vertically with no sense of time of day, and once a day has more than three
events the cell overflows. There is no way to see when a day is actually free.

## Goal

Clicking a day in the month grid opens a week view for the week containing that
day, showing all seven days as columns against a 24-hour vertical axis, with
events positioned and sized by their real start and duration.

## Non-goals

- Day view (single column). The week already answers "when am I free today".
- Timezone handling. The app stores tz-naive local wall time; that does not change.
- Server-side rendering of the week. It is a client view over the same data.

## Backend

No changes. `GET /api/events?from=&to=` already accepts a window and expands
recurring masters within it (`pages/calendar/models.py:_expand`). Create, edit,
delete, and skip-occurrence endpoints are unchanged and reused as-is.

The week fetch uses `from=<sunday>T00:00` and `to=<saturday>T23:59:59.999999`.

The bounds are compared as text against stored ISO strings, so a `T23:59`
upper bound sorts *below* a stored `T23:59:00` and silently drops the last
minute of the range. The month view had the same off-by-one; both now send a
bound that sorts above any stored seconds.

## Navigation

State lives in the URL hash on the existing `/calendar` route:

- `#week=YYYY-MM-DD` (any date in the target week) — week view
- no hash — month view

Clicking a `.cal-day` cell sets `location.hash`. A `hashchange` listener
re-renders. Browser back returns to the month grid and refresh restores the
week, both without extra code.

Both cards are `.card`, which is `display: flex` — that outranks the `hidden`
attribute, so `#cal-month[hidden]` and `#cal-week[hidden]` need an explicit
`display: none` (the same rule `.sat-quiz` and `.modal-backdrop` already carry).

Header behaviour in week mode:

- `#cal-label` reads `Aug 1 – 7, 2026` (year omitted on the first date when both
  dates share it).
- `#cal-prev` / `#cal-next` step by one week instead of one month.
- `#cal-today` jumps to the week containing today.
- A back-to-month button appears left of the label, using the existing
  `chevron-left`-style `icon-btn` treatment with a `layout-grid` icon.

## Layout

```
         Sun   Mon   Tue   Wed   Thu   Fri   Sat
 all-day [ ...................................... ]
  12 AM  |     |     |     |     |     |     |
   1 AM  |     |     |     |     |     |     |
   ...                                              (scrolls)
  11 PM  |     |     |     |     |     |     |
```

- Header row: weekday name + date number, today marked with the existing
  `.is-today` token treatment.
- All-day strip: its own row above the scroll container. Events with
  `all_day` true render here as full-width chips in the day column, wrapping
  vertically. The strip grows to fit; it does not scroll.
- Hour grid: a scroll container holding 24 rows at 60px each (1440px total).
  Hour labels sit in a fixed left gutter. The seven day columns are a CSS grid
  backdrop; event blocks are absolutely positioned over it.

Event block geometry, per day column:

```
top    = (startMinutesFromMidnight / 1440) * 1440px
height = max(durationMinutes, 20)          // 20px floor so a 5-min event is tappable
```

Events with no `end_at` are treated as 30 minutes for layout only; the stored
value stays null.

On open the container scrolls to 7 AM, or to the now-line when the current week
is in view.

## Overlap

Within a day, sort by `start_at`. Walk the list building groups: an event joins
the current group if it starts before the group's running maximum end. Each
group of `n` events splits the column width into `n` equal slots, assigned in
sort order — `left = (i/n)*100%`, `width = (1/n)*100%`, with a 2px gutter.

This is deliberately the simple version: it does not reclaim width when a late
event in a group does not actually overlap an earlier one. Acceptable for a
single-user calendar.

## Interaction

### Empty slot

- **Left-click** — an inline draft block appears at the nearest 30-minute slot
  containing a focused text input. Enter POSTs `{title, start_at, end_at}` with
  a one-hour duration. Escape, or blur with an empty title, discards it. Only
  one draft exists at a time; opening a second discards the first. Saving is
  latched: Enter removes the input, which fires `blur`, which would otherwise
  POST the same event twice.
- **Right-click** — context menu: *New event* (opens the existing modal
  prefilled with that day and time), *New all-day event* (modal prefilled with
  the date and `all_day` checked).

### Existing event

- **Left-click** — the existing edit modal, unchanged.
- **Right-click** — context menu: *Edit*, *Duplicate*, *Delete*, and
  *Skip this occurrence* shown only when the event carries `occurrence_of`.
  - Duplicate POSTs the same fields with a new id — no new endpoint.
  - Delete calls `DELETE /api/events/:id`. For an occurrence it deletes the
    master, so the menu shows *Delete series* for those, keeping the
    distinction from *Skip this occurrence* explicit.
  - Skip calls `POST /api/events/:id/skip` with the occurrence start.

### Context menu

One reusable `<div class="ctx-menu" hidden>` in the template, repositioned and
repopulated per invocation. Closes on outside click, Escape, or scroll.
`contextmenu` is prevented only inside the week grid.

### Drag

Pointer events (`pointerdown`/`pointermove`/`pointerup` with capture) so mouse
and touch share one path.

- Drag the block body: move. Both day (column) and time change. Snap to 15
  minutes.
- Drag the bottom 8px: resize. End time only, floor of 15 minutes.
- A 4px movement threshold separates a drag from a click, so left-click-to-edit
  still works.
- On release, PATCH `start_at`/`end_at`. On error, re-render from the last good
  state and show the existing alert path.
- Dragging an occurrence of a recurring event edits the master, which moves the
  whole series. To avoid a surprising edit, dragging an occurrence is disabled;
  the block gets `cursor: default` and drag handlers bail early.

## Now-line

A 1px line with a 6px dot at the left edge, drawn in today's column at the
current time. Rendered only when today falls inside the displayed week.
Updated on a 60-second interval that is cleared when leaving week view.

## Files

| File | Change |
|---|---|
| `static/js/calendar-week.js` | New. Week rendering, layout math, overlap grouping, drag, context menu, now-line. Exposes `renderWeek(dateKey)` / `destroyWeek()`. |
| `static/js/calendar.js` | Hash routing, month/week toggle, header controls. Month rendering unchanged. |
| `static/css/app.css` | New `.cal-week*` block. Tokens only, no hex literals. |
| `templates/calendar.html` | Week container, all-day strip, context menu element, back-to-month button. Load `calendar-week.js`. |
| `tests/test_calendar.py` | Assert `/calendar` still renders and the week window query returns the right rows. |

Splitting week rendering into its own file keeps `calendar.js` focused on the
month grid and routing; the week file is the larger of the two and stands alone.

## Testing

Server behaviour is unchanged, so tests cover the data contract, not the DOM:

1. `GET /api/events` with a seven-day window returns events inside it and
   excludes events outside it.
2. A recurring master expands to the correct occurrences inside a week window.
3. An occurrence added to EXDATE is absent from the week window.
4. `/calendar` returns 200 and includes the week container element.

Client behaviour (drag, overlap, draft creation) is verified manually in the
browser — the project has no JS test harness and adding one for this is not
justified.

## Estimate

3–4 hours. Drag is roughly 1.5 of those; layout and overlap about 1; routing,
context menu, and CSS the rest.
