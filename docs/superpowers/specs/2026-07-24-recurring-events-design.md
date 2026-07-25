# F.R.I.D.A.Y. — Recurring Events Design (Spec L)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (events model + `/api/events`).

## 1. Context

The calendar has no repetition — "standup every weekday", "rent on the 1st" must
be created one by one. Add recurrence via an **RRULE** string on an event, expanded
to occurrences at read time. Real-life-critical calendar gap.

## 2. Goals / Non-goals

**Goals**
- An optional `rrule` (RFC 5545) column on `events`.
- `list_events(from, to)` expands recurring masters into occurrences within the
  window.
- Create/edit recurrence via the agent tools and the event form.
- "This event only" vs "this and future" edit/delete semantics — minimal version.

**Non-goals**
- A full iCal import/export (could reuse the same lib later; not now).
- Arbitrary per-occurrence overrides/exceptions beyond a simple `EXDATE` skip.
- Timezone-per-rule complexity beyond the user's single home tz.

## 3. Design

**Lib:** `dateutil.rrule` (parse + expand). No hand-rolled recurrence math.

**Data:** `events.rrule TEXT NULL`. A row with `rrule` is a **master**; its
`start_at` is DTSTART. Non-recurring rows unchanged.

**Expansion:** `list_events(from, to)`:
- Non-recurring rows: as today (filtered by window).
- Masters: `rrulestr(rrule, dtstart=start_at)` → occurrences in `[from,to]`; emit
  synthetic occurrence dicts `{...master, start_at: occ, end_at: occ+duration,
  occurrence_of: master.id}` (duration = master `end_at - start_at`).

**Edit/delete of one occurrence:** append the occurrence's datetime to the master's
`EXDATE` (skip it) and, for edit, create a standalone event for the new values.
"This and future": split — set `UNTIL` on the master before the date, create a new
master from the date. Keep this the *only* two operations; no deeper override model.

**Tools:** `create_event`/`update_event` gain an optional `rrule` param.

## 4. Testing

- Unit: expand a weekday RRULE across a window → correct occurrence dates,
  durations preserved.
- Unit: EXDATE skip removes one occurrence; split (UNTIL + new master) yields the
  right before/after sets.
- Unit: non-recurring events unaffected.

## 5. Risks

- **DST/tz** in expansion — anchor DTSTART in the user's tz; `dateutil` handles the
  arithmetic.
- **Unbounded rules** in a huge window — always expand within the requested
  `[from,to]` only; never materialise infinite series.
- **API shape** — occurrences carry `occurrence_of` so clients know they're virtual;
  editing routes through the master.
