# F.R.I.D.A.Y. — On-Device Calendar/Todo UI Design (Spec D)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (app on Vercel + `/api/*`), Spec C (ESP32 firmware — WiFi,
display, config, state machine).
**Related:** Spec B (`/api/voice`) — voice mutates the same data this UI reads.

## 1. Context

Spec C's board is voice-only: its display shows four voice states plus
transcript/reply text. Spec D turns the same Waveshare ESP32-S3 7-inch board into
a **glanceable calendar/todo panel** — a wall/desk display that shows today's
schedule and open todos, refreshed from the cloud app, and reflects changes made
by voice, phone, or web.

This is the "always-on Iron-Man panel" half of the board. It reuses everything
Spec C already stands up (WiFi, TLS, NVS config, LVGL, the `SERVER_URL` +
`VOICE_TOKEN` pair) and adds a read-mostly data screen alongside the voice loop.

**Read-mostly by design.** The board is a viewer first. Mutation on-device is
limited to one safe gesture (tap a todo to toggle done); everything else
(create/edit/delete) stays with voice and the web app. This keeps the firmware
small and avoids a full touch-keyboard editing stack on the panel.

## 2. Goals / Non-goals

**Goals**
- Show **today + next few days** of events and the **open todo** list, on-panel,
  auto-refreshing.
- Reflect changes from any source (voice/web/phone) within one refresh interval.
- One on-device mutation: **tap todo → toggle done** (`PATCH /api/todos/<id>`).
- Coexist with Spec C's voice loop on the same board — voice takes over the
  screen while active, UI screen resumes on `IDLE`.
- Same monochrome, icons-only design language as the web app (no emoji).
- All config reused from Spec C (no new secrets).

**Non-goals**
- On-device event/todo **creation or text editing** (voice + web own that).
- Month-grid calendar view. Agenda/list only — legible at a glance across a room.
- Offline write queue / conflict resolution. If a `PATCH` fails, revert the row
  and let the next refresh reconcile.
- Auth beyond the shared `VOICE_TOKEN` bearer (single-user device, HTTPS only).
- Multi-board sync, per-board layout config, theming UI.

## 3. Data source (existing `/api/*`)

No new server endpoints. Spec D consumes the Spec A CRUD API read-side plus one
write:

| Call | Use |
|------|-----|
| `GET /api/events?from=<ISO>&to=<ISO>` | agenda window (today .. +N days) |
| `GET /api/todos?done=false` | open todo list |
| `PATCH /api/todos/<id>` `{done:true|false}` | tap-to-toggle |

**Event fields:** `id, title, start_at, end_at, all_day, location, notes`.
**Todo fields:** `id, title, due_at, notes, done`.

**Open question (§9):** the current `/api/*` routes authenticate for the browser
session, not a bearer token. Spec D needs the same `Authorization: Bearer
<VOICE_TOKEN>` gate that Spec B put on `/api/voice` extended to (at least) the
GET reads and the todo PATCH — or a small read-only `/api/board` aggregate
behind that token. Pick one in the plan; do **not** expose `/api/*` unauthenticated.

## 4. Screen model (LVGL)

Two screens; the state machine owns which is visible.

**Panel screen (default, when voice idle):**
```
+------------------------------------------------+
| Thu Jul 24            [wifi] [sync 7:49p]       |  header: date, status
+---------------------+--------------------------+
| TODAY                | TODOS (open)             |
|  09:00  Standup      |  [ ] Ship Spec D         |
|  12:30  Lunch w/ K   |  [ ] Call dentist  (due) |
|  --:--  (all-day) …  |  [ ] Buy cables          |
|                      |                          |
| TOMORROW             |                          |
|  10:00  Review       |                          |
+---------------------+--------------------------+
```
- Left column: agenda grouped by day (Today, Tomorrow, then dated). All-day
  events pinned to the top of their day.
- Right column: open todos, ordered as the API returns them (open first, due
  date, then created). Overdue `due_at` gets an icon marker, not color (monochrome).
- Header: date, WiFi indicator, last-sync time. Reuses Spec C indicators.
- Tap target = a todo row → toggle done (optimistic, see §6).

**Voice overlay:** Spec C's existing voice-state screen. Shown on wake, hidden
back to the panel on return to `IDLE`. Spec C's four states are unchanged; Spec D
only adds "what to show when *not* in a voice interaction".

## 5. Refresh / state machine (extends Spec C)

Spec C's loop gains a background data concern. The voice states are untouched;
Spec D adds a periodic refresh that runs only while idle.

```
IDLE (Spec C) additionally:
  - on entering IDLE, ensure PANEL screen is shown
  - a refresh timer (default 60s) fires -> REFRESH
REFRESH:
  - GET events window + GET open todos
  - on success: rebuild panel model, update "last sync", -> IDLE
  - on failure: keep stale data, show stale indicator, backoff, -> IDLE
Voice states (LISTENING/THINKING/SPEAKING): show voice overlay; suspend refresh.
On return to IDLE after SPEAKING: force one immediate REFRESH (voice may have
  mutated data), then resume the timer.
```

- **Refresh is idle-only.** Never fetch mid-utterance; audio + TLS on one core is
  already tight (Spec C §10). One request type in flight at a time.
- **Post-voice refresh** is the mechanism that makes "add a todo by voice" appear
  on the panel seconds later — no push, no websocket. Polling is enough for a
  single-user glance panel; keep it (YAGNI on realtime).

## 6. On-device mutation (tap-to-toggle)

The one write path, kept trivial and safe:

1. Tap a todo row → immediately flip its checkbox in the LVGL model (optimistic).
2. Fire `PATCH /api/todos/<id>` `{done: <new>}` with the bearer token.
3. On 2xx: leave it; the next refresh confirms.
4. On failure/timeout: **revert** the row to its prior state, show a brief
   inline error marker. No retry queue — the user can tap again.

Rationale: a stale toggle is self-correcting on the next `GET`; a persisted retry
queue is exactly the offline-write complexity §2 rules out.

## 7. Configuration

Nothing new. Reuse Spec C's NVS/`sdkconfig`: `WIFI_*`, `SERVER_URL`, `VOICE_TOKEN`.
Two optional tunables (with defaults, so zero-config works):

- `PANEL_REFRESH_SECS` (default 60)
- `AGENDA_DAYS` (default 3) — size of the `from..to` events window.

## 8. Project layout (extends Spec C `firmware/main/`)

```
main/
  panel.c/.h    # NEW: LVGL agenda+todo screen; build model from JSON
  data.c/.h     # NEW: GET events/todos, PATCH todo; JSON -> structs
  main.c        # MODIFIED: register refresh timer, panel<->voice screen swap
  net.c/.h      # REUSED: HTTPS client, bearer header (from Spec C)
  ui.c/.h       # REUSED: voice overlay screen (Spec C)
```

`data.c` parses JSON with the ESP-IDF-bundled `cJSON`; no new component.
`panel.c` owns only layout + model; `data.c` owns only I/O + parse.

## 9. Open questions (resolve in plan)

1. **API auth for the board.** Extend bearer-token auth to the read `/api/*`
   routes + todo PATCH, or add a token-gated `/api/board` aggregate that returns
   `{events, todos}` in one round-trip. Aggregate = one request/refresh (less
   TLS churn on-device) but a new endpoint. **Lean: aggregate**, it also halves
   handshakes. Decide before firmware work.
2. **Timezone.** `start_at`/`due_at` are ISO strings; the panel must render in the
   user's local tz. Store tz in settings (server) and format on-device, or have
   the aggregate pre-format display strings? Pre-formatting server-side keeps
   tz/DST logic off the microcontroller (**lean: server formats display fields**,
   board renders opaque strings).
3. **Touch on the Waveshare panel.** Confirm the BSP exposes the touch controller
   to LVGL input; if capacitive touch is flaky, fall back to read-only (drop §6),
   which keeps the whole spec valid minus one gesture.

## 10. Testing

Same split as Spec C (§9):
- **Host-testable pure units:** JSON→model parsing in `data.c`, and the
  agenda-grouping logic (events → Today/Tomorrow/dated buckets). Unit-test on host
  with sample API payloads.
- **On-device manual:** panel renders current data; edit via web/voice appears
  within one refresh; tap toggles a todo and it survives the next refresh; failed
  PATCH reverts; voice overlay swaps in and back out; stale indicator on WiFi drop.
- No realtime/websocket to test — polling only.

## 11. Risks

- **Endpoint auth (open Q1)** — the board must not force `/api/*` open. Gate it
  first; this is the one hard blocker.
- **Touch reliability** — mitigated by the read-only fallback (Q3).
- **Screen contention voice↔panel** — one owner (state machine) swaps screens;
  refresh suspended during voice avoids concurrent LVGL + audio pressure.
- **Clock/tz drift** — server-formatted display strings (Q2) keep DST logic off
  the device; board still needs SNTP for the header clock (already needed by TLS).

## 12. Phase 3 spec set (updated)

| Spec | Subsystem | Status |
|------|-----------|--------|
| A | Cloud migration (Vercel + Postgres) | Approved, implemented |
| B | Voice API (`/api/voice`) | Approved, implemented |
| C | ESP32 voice client | Approved, impl gated on wake-word |
| D | On-device calendar/todo UI (this doc) | Draft — resolve §9, then plan |
