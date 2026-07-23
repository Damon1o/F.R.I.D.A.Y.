# F.R.I.D.A.Y. — Cloud Migration Design (Spec A)

**Date:** 2026-07-23
**Status:** Approved (design), pending implementation plan
**Depends on:** none (foundation)
**Blocks:** Spec B (Voice API), Spec C (ESP32 firmware)

## 1. Context

F.R.I.D.A.Y. currently runs as a local, single-user Flask app bound to
`127.0.0.1`, with SQLite (`friday.db`) accessed through a thin stdlib `sqlite3`
layer. The next arc moves the whole system to the cloud so a Waveshare ESP32-S3
board can reach a hosted voice endpoint.

That arc is **three independent subsystems**, specced and built in order:

| Spec | Subsystem | Scope |
|------|-----------|-------|
| **A (this doc)** | Cloud migration | Whole Flask app → Vercel serverless; SQLite → Postgres |
| B | Voice API | `POST /api/voice`: wav → whisper.cpp → agent → piper → wav |
| C | ESP32 firmware | On-device `hey friday` WakeNet → record → HTTPS POST to B → play reply (in `/firmware`, ESP-IDF) |

This spec covers **A only**. B and C are out of scope here; A is their
foundation because they require the app to already run on Vercel with a
persistent (non-SQLite) database.

### Identity change (explicit)

The project's original identity — *local, single-user, `127.0.0.1`, zero
external network* (see `CLAUDE.md` and Phase 1 spec) — is deliberately
superseded for the cloud deployment. `CLAUDE.md` must be updated as part of this
work to reflect: hosted on Vercel serverless, Postgres data store, secrets via
Vercel env. The "no external CDN / self-host assets / no emojis / Lucide icons"
design rules are **retained**.

## 2. Goals / Non-goals

**Goals**
- Deploy the existing Flask app (web UI + existing `/api/*` routes) to Vercel
  serverless with no behavioral change to pages or the assistant.
- Replace the SQLite data layer with Postgres (Neon) behind the same
  `core/db.py` interface, so models change as little as possible.
- Keep the test suite meaningful by running it against real Postgres.
- Provide a one-shot script to migrate existing `friday.db` data to Postgres.

**Non-goals**
- The voice endpoint, whisper/piper bundling, or any audio handling (Spec B).
- ESP32 firmware (Spec C).
- Rearchitecting routes, templates, the agent loop, or the design system.
- Multi-user / auth (still single-user).

## 3. Runtime: Flask on Vercel

Vercel's Python runtime serves functions from `api/`. A single WSGI entrypoint
exposes the existing app:

```
api/index.py      # from app import create_app; app = create_app(); handler = app (WSGI)
vercel.json       # route every path to api/index.py; set Python runtime + maxDuration
requirements.txt  # existing deps + psycopg[binary]
```

`vercel.json` rewrites all routes (`/`, `/calendar`, `/todos`, `/settings`,
`/api/*`, `/static/*`) to the Flask handler. Static assets under `static/`
continue to be served by Flask via `url_for('static', …)`; no CDN is
introduced (design rule retained).

**Cold starts:** each cold invocation re-imports the app and opens a DB
connection. This is inherent to serverless and makes the app feel slower than
localhost. Mitigated by using Neon's **pooled** endpoint (below); no code-level
warm-keeping in this spec.

## 4. Data layer: SQLite → Postgres

### 4.1 Driver and connections

- Use **psycopg 3** (`psycopg[binary]`).
- Connect to **Neon's pooled connection string** (`DATABASE_URL`), which fronts
  Postgres with PgBouncer — required so many short-lived serverless invocations
  don't exhaust connections.
- Keep the existing shape: one connection per request stored on Flask `g`,
  closed on `teardown_appcontext`.

New `core/db.py` (same public functions — `get_db`, `close_db`, `init_db`,
`query`, `execute`, `init_app`):

```python
import os, psycopg
from psycopg.rows import dict_row
from flask import current_app, g

def get_db():
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db

def query(sql, params=(), *, one=False):
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows

def execute(sql, params=(), *, returning=False):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone() if returning else None
    db.commit()
    return row   # e.g. {"id": 42} when `returning` and SQL ends with RETURNING id
```

Note: `row_factory=dict_row` returns dicts. Models currently rely on
`sqlite3.Row` (index + key access). Models read rows by **key**, so `dict_row`
is compatible; any positional `row[0]` access must be audited and keyed.

### 4.2 Schema (`schema.sql` → Postgres dialect)

- `id INTEGER PRIMARY KEY AUTOINCREMENT` → `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`.
- `DEFAULT (datetime('now'))` → `DEFAULT now()` (column stays `TEXT`; store ISO
  strings as today, or cast — see below).
- Keep `TEXT` for ISO-8601 datetime columns and `INTEGER` (0/1) for booleans, to
  avoid touching model logic. `now()` returns a timestamp; to keep columns
  `TEXT`, defaults become `DEFAULT to_char(now() at time zone 'utc',
  'YYYY-MM-DD"T"HH24:MI:SS')` **or** the app sets `created_at` explicitly. The
  plan will pick one; default to app-set timestamps for clarity.
- `CREATE TABLE IF NOT EXISTS` is retained; `init_db()` runs it on cold start
  (idempotent, cheap).

### 4.3 SQL in models

Two mechanical changes across `pages/*/models.py` and `pages/kiko/messages.py`:

1. **Placeholders:** SQLite `?` → psycopg `%s` in every SQL string. This is the
   widest-reaching edit; it is purely mechanical.
2. **Insert IDs:** replace `cur.lastrowid` with `RETURNING id` +
   `execute(..., returning=True)`. Audit each INSERT that reads the new id.

No other model logic changes.

## 5. Config

`config.py`:
- Add `DATABASE_URL = os.environ["DATABASE_URL"]` (Neon pooled).
- Remove `DB_PATH` (SQLite-only). Local development uses a local Postgres or a
  Neon dev branch via the same `DATABASE_URL`.
- `DEEPSEEK_*` unchanged.

Vercel env vars: `DATABASE_URL`, `DEEPSEEK_API_KEY` (+ base url/model if
overridden).

## 6. Data migration

`scripts/sqlite_to_pg.py`: one-shot, run locally once.
- Read every row from `friday.db` (settings, events, todos, messages).
- Insert into Postgres, preserving values. IDs may be reassigned (single user;
  no external references to event/todo ids). If id preservation matters, use
  `OVERRIDING SYSTEM VALUE` on the identity columns.
- Idempotency not required (run once); document the command in the plan.

## 7. Testing

Tests run against **real Postgres** so they exercise the production dialect
(placeholders, identity columns, `RETURNING`).

- `conftest.py` `app` fixture: connect to a disposable Postgres (local Docker
  `postgres` or a Neon test branch) via a `TEST_DATABASE_URL`; create a fresh
  schema per test session and truncate (or use a fresh schema/transaction
  rollback) between tests for isolation.
- Keep the existing empty-`DEEPSEEK_API_KEY` override so the LLM stays faked.
- All 34 current tests must pass unchanged in behavior after the port.
- **CI cost:** the pipeline now requires a Postgres service. This is the
  accepted trade for dialect-accurate tests (dual-dialect abstraction was
  rejected as over-engineering).

## 8. What stays exactly the same

Routes, Jinja templates, static assets/design system, the DeepSeek agent loop
(`pages/kiko/agent.py`), tools, and all request/response contracts. A user
hitting the deployed app sees identical behavior; only the host and database
change.

## 9. Risks

- **Cold-start latency** on serverless; pooled Neon mitigates connection cost
  but not import/startup. Acceptable for a single-user app; revisit if painful.
- **Connection limits** — must use the pooled endpoint, not the direct one.
- **250MB / timeout limits** are a Spec B concern (whisper/piper), not A; noted
  so A's `vercel.json` `maxDuration` is set with B in mind (Pro plan).
- **Postgres in tests** adds CI infra; mitigated by Docker/Neon branch.

## 10. Open items folded into the plan

- Exact `created_at`/`updated_at` default strategy (app-set vs SQL `to_char`).
- Whether to preserve row ids in migration.
- Test isolation mechanism (truncate vs per-test transaction rollback).
