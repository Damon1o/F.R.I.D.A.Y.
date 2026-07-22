# Kiko — Phase 1 (Core) Design

**Date:** 2026-07-21 (revised 2026-07-22)
**Status:** Approved (design), pending implementation plan
**App:** Kiko — a personal, voice-driven AI productivity web app (single user, localhost)

> **2026-07-22 revision — Stitch-driven frontend.** The design system is now sourced
> from the "Glassmorphic AI Productivity Suite" Stitch project export (4 screens:
> Dashboard, Calendar, Task Manager, Settings) instead of the git-history glassmorphism
> CSS. See §11. Adds a **Settings** page (`/settings`) beyond the original scope.

## 1. Overview

Kiko is a personal productivity web app run locally on the user's machine. The full
product spans five subsystems built in four phases; each phase ships a usable app and
gets its own spec → plan → implementation cycle.

| Phase | Delivers | Usable after? |
|-------|----------|---------------|
| **1 — Core** *(this spec)* | Flask shell + SQLite + Dashboard + Calendar CRUD + To-Do CRUD | Yes — full manual productivity app, no AI |
| 2 — Assistant | DeepSeek chat + tool-calling that creates/edits events & todos from natural language | Yes |
| 3 — Voice | Browser mic → whisper-local transcription → Phase 2 assistant | Yes |
| 4 — Notify | Scheduler + Discord push (event reminders, todo due dates, daily digest, on-demand) | Yes |

This document specifies **Phase 1 only**. Later phases are sketched for context and to
keep Phase 1 decisions forward-compatible, but are out of scope here.

### Prior work

The repository's working tree is currently empty — commit `74c01a5`
("chore: remove deprecated project files") deleted all source. The prior build remains
in git history at `HEAD~1` (`bb6176f`) and is reused as reference/base material:

- Flask app shell (`app.py`, `config.py`) + blueprint-per-page pattern under `pages/`
- Glassmorphism design system: `static/css/tokens.css`, `static/css/depth.css`,
  `static/css/dashboard.css`
- Calendar page + FAB chat widget + whisper hooks

Recover any prior file with `git show bb6176f:<path>`.

## 2. Scope

**In scope (Phase 1):**

- Flask application shell with a topbar/sidebar/content app layout (revived from history).
- SQLite persistence for events and todos.
- Dashboard page: today's agenda (events + open todos) with quick-add.
- Calendar page: month view; create/edit/delete events.
- To-Do page: list; create/edit/complete/delete tasks.
- Settings page (`/settings`): static/placeholder controls (theme, profile stub); no
  persistence in Phase 1. Added from the Stitch design; see §11.
- An always-on Kiko assistant panel (right column) — inert placeholder in Phase 1,
  wired in Phase 2. Replaces the earlier "chat FAB" concept.
- Pytest test suite covering models and JSON endpoints.

**Out of scope (deferred):**

- Any AI / DeepSeek / LLM integration (Phase 2).
- Voice / whisper (Phase 3).
- Discord notifications / scheduler (Phase 4).
- Authentication / multi-user (never — personal localhost app).
- Recurring events, task priority, tags, subtasks, reminders (future; not Phase 1).

## 3. Key technical decisions

| Decision | Choice | Rejected alternative & why |
|----------|--------|----------------------------|
| Database | SQLite via stdlib `sqlite3`, one `schema.sql`, thin `core/db.py` helper | SQLAlchemy / ORM — overkill for a solo single-file DB |
| Frontend | Server-rendered Jinja templates + vanilla JS `fetch`, no build step | React/SPA — unnecessary toolchain; stack is HTML/CSS/JS |
| Auth | None; binds to `127.0.0.1`, single user | Login/session — YAGNI on a personal machine |
| Config | `.env` via `python-dotenv`; `config.py` reads it | Phase 1 needs no secrets, but scaffold for Phases 2–4 keys |
| Icons | Self-hosted, pinned Lucide (SVG); Stitch's Material Symbols mapped to Lucide equivalents | Material Symbols / emojis / Unicode — CDN + banned per project rule |
| Styling | Hand-authored CSS from **Stitch export** M3 tokens (§11); no Tailwind | Tailwind CDN (Stitch default) — CDN banned; git-history tokens — superseded by Stitch |
| Fonts | **Hanken Grotesk**, self-hosted `@font-face` | Google Fonts CDN (Stitch default) — CDN banned |

## 4. Data model

SQLite database file at `kiko.db` (git-ignored). Schema in `schema.sql`, applied by
`core/db.init_db()` on startup if tables are absent. Datetimes stored as ISO-8601 text
(UTC), rendered in local time by the frontend.

```sql
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    start_at   TEXT    NOT NULL,          -- ISO-8601
    end_at     TEXT,                      -- ISO-8601, nullable
    all_day    INTEGER NOT NULL DEFAULT 0,-- 0/1 boolean
    location   TEXT,
    notes      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    due_at       TEXT,                       -- ISO-8601, nullable
    done         INTEGER NOT NULL DEFAULT 0, -- 0/1 boolean
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT                        -- set when done flips to 1
);
```

## 5. Module structure

```
app.py                    Flask app factory; registers blueprints; init_db() on boot
config.py                 loads .env, exposes settings (DB path, host, port)
schema.sql                table definitions
core/
  __init__.py
  db.py                   get_db(), init_db(), query()/execute() row helpers
pages/
  __init__.py
  dashboard/
    __init__.py
    routes.py             GET / -> today's events + open todos + chat FAB placeholder
  calendar/
    __init__.py
    routes.py             GET /calendar (page) + /api/events CRUD
    models.py             event row <-> dict, validation, DB queries
  todos/
    __init__.py
    routes.py             GET /todos (page) + /api/todos CRUD
    models.py             todo row <-> dict, validation, DB queries
  settings/
    __init__.py
    routes.py             GET /settings (page only; no persistence Phase 1)
static/
  css/  tokens.css, depth.css, shell.css, dashboard.css, calendar.css,
        todos.css, settings.css, kiko-panel.css
  js/   theme.js, calendar.js, todos.js, dashboard.js
  vendor/lucide/          self-hosted pinned Lucide assets
  vendor/fonts/           self-hosted Hanken Grotesk @font-face files
templates/
  base.html               3-col shell: left nav + main + right Kiko panel + glass topbar
  _kiko_panel.html        always-on assistant panel partial (inert Phase 1)
  dashboard.html
  calendar.html
  todos.html
  settings.html
tests/
  conftest.py             app + in-memory SQLite fixtures
  test_events.py
  test_todos.py
  test_pages.py           smoke: /, /calendar, /todos, /settings return 200 with markers
requirements.txt          flask, python-dotenv, pytest
.env.example
.gitignore                kiko.db, .env, __pycache__
```

Each page is a self-contained blueprint owning its routes, model, template, JS, and
tests. `core/db.py` is the only shared data dependency.

## 6. JSON API contract

All endpoints accept/return JSON. Validation errors return `400` with
`{"error": "<message>"}`. Missing resources return `404`.

**Events**

| Method + path | Body / query | Returns |
|---|---|---|
| `GET /api/events?from=<iso>&to=<iso>` | range filter (both optional) | `[event, …]` |
| `POST /api/events` | `{title, start_at, end_at?, all_day?, location?, notes?}` | `201 {event}` |
| `PATCH /api/events/<id>` | any subset of event fields | `{event}` |
| `DELETE /api/events/<id>` | — | `204` |

**Todos**

| Method + path | Body | Returns |
|---|---|---|
| `GET /api/todos?done=<0\|1>` | optional filter (default: all) | `[todo, …]` |
| `POST /api/todos` | `{title, due_at?, notes?}` | `201 {todo}` |
| `PATCH /api/todos/<id>` | subset incl. `{done}` (sets/clears `completed_at`) | `{todo}` |
| `DELETE /api/todos/<id>` | — | `204` |

Validation rules: `title` required and non-empty; datetimes must parse as ISO-8601;
`end_at` (if present) must be ≥ `start_at`.

## 7. Pages

- **Dashboard (`/`)** — Greeting + today's date. Two panels: **Today's events**
  (events whose `start_at` falls today, sorted by time) and **Open tasks** (todos with
  `done = 0`, overdue flagged). A quick-add input for each. Plus Stitch's **Weekly Focus**
  and **Recent Activity** cards. The Kiko assistant panel (right column, from `base.html`)
  is inert in Phase 1 with a "coming soon" note; replaces the old chat FAB.
- **Calendar (`/calendar`)** — Month grid (reuse prior calendar CSS/JS). Click a day to
  add an event; click an event to edit/delete via a modal. Fetches `/api/events` for the
  visible month range.
- **To-Do (`/todos`)** — Single list. Add task (title + optional due date). Check to
  complete (strikethrough, moves to bottom / filtered). Click to edit; delete button.
  Overdue tasks visually flagged. New page — styled with `todos.css` using existing
  design tokens; layout designed with the frontend-design skill during implementation.

- **Settings (`/settings`)** *(new, from Stitch)* — Static/placeholder controls only:
  theme switch (reuses `theme.js`), profile stub, app-info section. No persistence in
  Phase 1; a page-only blueprint. Layout from the Stitch Settings screen.

All pages extend `base.html` (glass topbar + left icon/label nav + right Kiko panel),
use self-hosted Lucide icons, and share the Stitch-derived token system (§11).
Dark default with a light theme toggle.

## 8. Testing

Pytest with an app factory that accepts an in-memory SQLite database for isolation.

- **Model tests** — create/read/update/delete for events and todos; validation
  rejections (empty title, bad datetime, `end_at < start_at`); `completed_at` set/cleared
  on `done` toggle.
- **Endpoint tests** — each route's happy path + error codes (400 invalid body,
  404 missing id); `GET /api/events` range filtering; `GET /api/todos?done=` filtering.
- **Page smoke tests** — `/`, `/calendar`, `/todos`, `/settings` each return 200 and
  contain expected markers (e.g. panel headings, page title). Settings is page-only.

## 9. Success criteria

Phase 1 is done when:

1. `flask run` (bound to `127.0.0.1`) serves Dashboard, Calendar, and To-Do pages.
2. A user can create, edit, and delete events via the calendar UI; they persist across
   restarts in `kiko.db`.
3. A user can create, complete, edit, and delete todos via the To-Do UI; they persist.
4. The dashboard shows today's events and open tasks accurately.
5. `pytest` passes with the suite in §8 green (incl. `/settings` smoke).
6. No emojis in the UI; all icons are self-hosted Lucide.
7. No external CDN requests: no Tailwind CDN, no Google Fonts — fonts and all assets
   are self-hosted. UI matches the Stitch reference screens (§11).

## 10. Forward-compatibility notes

- The always-on Kiko panel (right column) and `.env` scaffold exist so Phase 2 (DeepSeek
  assistant) can slot in without restructuring.
- Event/todo models expose clean create/update functions the Phase 2 tool-calling layer
  will call directly (natural-language → action).
- Datetimes stored as ISO-8601 UTC so the Phase 4 scheduler can query "due within N
  minutes" without timezone ambiguity.

## 11. Design system — Stitch export

Source: the **"Glassmorphic AI Productivity Suite"** Stitch project (ID
`4222202996537344738`), 4 screens exported as PNG + HTML. The HTML is a **layout and
visual reference only** — none of its Tailwind/CDN output ships. We hand-author CSS
from its design tokens.

**Palette (monochrome, Material 3 semantic naming) → `tokens.css` custom props.**
Dark is the default theme. Representative dark values from the export:

| Token | Value | Token | Value |
|---|---|---|---|
| `--surface` | `#131313` | `--on-surface` | `#e5e2e1` |
| `--surface-container-low` | `#1c1b1b` | `--outline` | `#8e9192` |
| `--surface-container` | `#201f1f` | `--outline-variant` | `#444748` |
| `--surface-container-high` | `#2a2a2a` | `--secondary` | `#c8c6c6` |
| `--surface-variant` | `#353534` | `--primary-fixed` | `#e2e2e2` |

Light-theme values are derived (inverted lightness ramp) and toggled via the same
`theme.js` class-on-root mechanism (`darkMode: "class"` in the Stitch config). No hex
literals in component CSS — everything references a token.

**Glass / depth (`depth.css`).** Backdrop-blur layers over the surface tokens:
`--blur-panel` (left/right asides ~`blur-2xl`/`blur-3xl`), `--blur-topbar`
(`blur-xl`), semi-opaque container backgrounds (`surface-container/40` style alpha),
hairline borders (`--outline-variant`, `border-white/10` equivalent).

**Typography.** Body/UI font **Hanken Grotesk** (weights 400/500/600/700), self-hosted
as `@font-face` under `static/vendor/fonts/`. Stitch's `display-lg` / `headline-lg` /
`title` scales map to `--text-display-lg`, `--text-headline-lg`, etc.

**Icons.** Stitch uses **Material Symbols Outlined** (a CDN font — banned). Each glyph
maps to a self-hosted **Lucide** icon rendered through the existing `icons.html` macro.
Mapping table authored during implementation (e.g. `dashboard`→`layout-dashboard`,
`calendar_month`→`calendar`, `checklist`→`list-checks`, `settings`→`settings`,
`mic`→`mic`). No emoji, no Unicode glyph icons.

**Shell layout (`base.html`).** Three fixed columns from the Stitch screens:
- Left `aside` (w-64) — glass nav: brand "Kiko" + icon/label links (Dashboard,
  Calendar, Tasks, Settings), active-state highlight.
- Center `main` — sticky glass `header` (topbar) + page content.
- Right `aside` (w-80) — always-on **Kiko** assistant panel ("Kiko Bot" in the export):
  header, status, transcript/placeholder body. Inert in Phase 1. Collapses below `lg`.

**No-CDN guarantee.** All fonts, icons, and styles are self-hosted; the app makes zero
external network requests. Enforced by the page smoke tests asserting no
`cdn.tailwindcss.com` / `fonts.googleapis.com` / `fonts.gstatic.com` references in
rendered HTML.

**Reference assets.** Exported PNG + HTML per screen live at
`docs/design/stitch/` (copied from the download) for implementation reference.
