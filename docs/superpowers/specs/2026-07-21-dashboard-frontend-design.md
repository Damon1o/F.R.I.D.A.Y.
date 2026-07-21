# Dashboard Frontend Design

Date: 2026-07-21

## Purpose

Replace the current bare-bones layout (`static/css/style.css`, plain `base.html`
with a persistent chat aside) with a polished frontend matching the
`image.png` HR-dashboard-style mockup, reusing the design system already
built in `hr-dashboard/` (tokens, glassmorphism/neumorphism depth, layout
primitives). Adds a new Dashboard home page; restyles the existing Calendar
page; moves chat from a persistent sidebar into page-scoped widgets.

## Scope

- New `/` route: Dashboard page with mockup-style cards.
- Restyle existing `/calendar` route: month calendar grid, no persistent
  chat sidebar.
- Chat becomes two instances of one reusable widget, not a global aside:
  - Dashboard: a card that starts as a "welcome" empty state and grows into
    a full conversation on first message.
  - Calendar: a floating circular button (FAB) that expands into a compact
    chat overlay panel.
- Dashboard's Planned Absences / Future Events / Onboarding cards are
  **static placeholder markup** (no new models, no new routes) — purely
  decorative, matching the mockup's visual density since the app has no
  employee/onboarding/events-attendee data yet.
- Out of scope: real employee data, onboarding data, dark-mode toggle UI,
  authentication/user profile, any new backend models.

## Design System Reuse

- Copy `hr-dashboard/tokens.css` and `hr-dashboard/depth.css` into
  `static/css/` unchanged — both are generic (color/spacing/shadow/motion
  primitives + glass/neu utility classes), not HR-specific.
- New `static/css/dashboard.css`: the generic parts of
  `hr-dashboard/layout.css` (dashboard grid, top bar, sidebar, nav items,
  AI chat panel, view switcher, search, logo, scrollbar) plus the generic
  parts of `hr-dashboard/views.css` (`.card`, `.card-header/-title/-action`,
  empty-state, skeleton, `.ai-*` chat/welcome classes). Team/analytics/
  onboarding-progress-ring CSS is trimmed to just what the placeholder
  cards need (card + list-item shells, no charts).
- `static/css/style.css` is rewritten to hold only calendar-month-grid
  rules (day cells, day number, event pills), re-based on the new tokens
  instead of hardcoded hex colors.

## Pages & Routes

### `/` — Dashboard (new)

New blueprint `pages/dashboard/routes.py` (`dashboard_bp`), route `/`,
template `templates/dashboard.html` extending `base.html`.

Layout (top to bottom):
1. Top wide card — "Planned Absences": static list of 3-4 fake
   employee rows with fake leave-block pills (paid leave / vacation / sick
   leave), reusing `.leave-block` styles from `views.css`.
2. Bottom row, 3 cards:
   - "Future Events" — static placeholder event list (`.event-card`-style).
   - "Onboarding" — static placeholder onboarding list (name/role/task
     count, no progress ring — keep it simple).
   - AI Chat card (`#dash-chat`) — real, wired to `/api/chat`. Starts as
     `.ai-welcome` (orb, title, quick-action chips). First send swaps to a
     scrollable message list + input, growing the card.

### `/calendar` — Calendar (restyled)

Existing `pages/calendar/routes.py` route stays. `templates/calendar.html`
becomes a full-width card containing the month grid (nav prev/next month,
day cells, event pills), no side chat panel.

Adds a floating chat button (`#calendar-fab`), fixed bottom-right. Clicking
it lazily mounts a compact chat widget (`#fab-chat`) in a small panel above
the button, same `/api/chat` wiring as the dashboard card. Closing collapses
it back to just the button (DOM/state persists between opens within the
same page load — no need to persist across navigation).

### `base.html`

Drops `<aside class="chat-panel">` and the global `chat.js` include. Keeps
`<nav class="sidebar">` — restyled to hr-dashboard's `.sidebar`/`.nav-item`
pattern with two items: Dashboard, Calendar. Adds a `.top-bar` (logo, a
non-functional search input for visual parity with the mockup, a static
user-avatar placeholder — no auth exists, so this is decorative only).

## JS Architecture

Refactor `static/js/chat.js` into `static/js/chat-widget.js` exporting
`createChatWidget(container, { compact })`:
- Wires its own form/input/messages/token-usage elements scoped to
  `container` (not global `document.getElementById`).
- Tracks welcome-vs-conversation state internally for the dashboard card
  (`compact: false` starts in welcome mode; first send switches modes).
- `compact: true` (FAB panel) skips the welcome/orb view and starts directly
  as a small message list + input.
- Fixes the existing token-field mismatch: `/api/chat` returns
  `{ reply, input_tokens, output_tokens, total_tokens, budget_warning }`
  directly (not nested under `usage` as the old `chat.js` assumed) — the
  widget reads these top-level fields.

`dashboard.html` instantiates one widget for `#dash-chat`.
`calendar.html` instantiates one widget for `#fab-chat`, created on first
FAB click.

`static/js/calendar.js` keeps fetching events and rendering the month grid,
but:
- Fixes the endpoint path bug: fetches `/calendar/api/events` (the route
  that actually exists per `pages/calendar/routes.py`), not the current
  `/api/calendar/events` (404s today).
- Renders into the new card/grid class names from `dashboard.css`, keeping
  the existing `escapeHtml()` XSS guard on event titles.

Dashboard's static cards (Planned Absences, Future Events, Onboarding) are
plain Jinja-rendered HTML — no JS.

## Error Handling

Unchanged from current behavior: calendar fetch failure replaces the grid
with an inline error message; chat fetch failure appends an error bubble
to the conversation. No new failure modes introduced by this change.

## Testing

- Add `tests/test_dashboard.py`: Flask test-client check that `GET /`
  returns 200 and the response body contains the three card titles
  ("Planned Absences", "Future Events", "Onboarding") and the chat card's
  container id, following the existing test style in `tests/`.
- Existing `tests/test_router.py` / calendar/chat tests are unaffected
  (route paths and API contracts for `/api/chat` and
  `/calendar/api/events` are unchanged, only the frontend consuming them).
- No JS unit tests. Manual verification: run the Flask dev server, load
  `/` and `/calendar` in a browser, send a chat message on each surface,
  confirm the calendar event list still loads (this also verifies the
  endpoint-path bug fix), confirm the FAB expands/collapses.
