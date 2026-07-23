# Cloud Migration (Spec A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing F.R.I.D.A.Y. Flask app on Vercel serverless with Postgres (Neon) replacing SQLite, with no change to pages, routes, or the agent.

**Architecture:** Keep every route, template, and the DeepSeek agent loop untouched. Swap the `core/db.py` engine from stdlib `sqlite3` to psycopg 3 against a pooled Neon connection, port `schema.sql` to Postgres dialect, and change SQL placeholders (`?`→`%s`) plus insert-id reads (`lastrowid`→`RETURNING id`) in the four files that hold SQL. Add a thin WSGI entrypoint under `api/` and a `vercel.json`. A one-shot script copies existing `friday.db` rows into Postgres.

**Tech Stack:** Flask 3, psycopg 3 (`psycopg[binary]`), Postgres 16 (Neon prod, local Docker Postgres or Neon branch for tests/CI), Vercel `@vercel/python`.

## Global Constraints

- **Public DB functions stay the same:** `get_db`, `close_db`, `init_db`, `query`, `execute`, `init_app`. `query(sql, params=(), *, one=False)` and `execute(sql, params=())` keep their signatures; `execute` returns a live, already-committed cursor (so `.rowcount` and `.fetchone()` work). This is a deliberate refinement of Spec A §4.1 (no `returning=` kwarg) to keep model churn minimal.
- **Placeholders:** psycopg uses `%s`, never `?`. Every SQL string must use `%s`.
- **Rows are dicts:** connection uses `row_factory=dict_row`. Access columns by key only (`row["id"]`), never positional. All current models already key rows.
- **Timestamps stay TEXT ISO strings** stored by a SQL default, format `YYYY-MM-DD HH24:MI:SS` (matches the old SQLite `datetime('now')` output). Models keep passing no `created_at`/`updated_at`.
- **IDs are `BIGINT GENERATED ALWAYS AS IDENTITY`.** Boolean columns stay `INTEGER` 0/1.
- **Design rules retained:** no external CDN, self-host assets, no emoji, Lucide icons. (Only the "local/127.0.0.1/zero-network" identity is superseded.)
- **Secrets from env:** `DATABASE_URL`, `DEEPSEEK_*` from environment. No secrets in source.
- **LLM stays faked in tests** via empty `DEEPSEEK_API_KEY` (existing behavior).

---

## Prerequisite: a Postgres for tests

Tasks 1 and 3 need a real Postgres. The executor must have one reachable and export `TEST_DATABASE_URL` (default assumed by conftest if unset: `postgresql://postgres:postgres@localhost:5432/friday_test`).

Local Docker one-liner (documented, not a code step):

```bash
docker run -d --name friday-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=friday_test -p 5432:5432 postgres:16
```

---

## Task 1: Port the data layer to Postgres

The SQLite→Postgres swap is atomic: schema, engine, placeholders, and insert-id reads must all change together or the suite cannot run. Deliverable: **all 34 existing tests pass against real Postgres.** No new behavior — the existing suite is the gate.

**Files:**
- Modify: `requirements.txt`
- Modify: `schema.sql` (full rewrite to Postgres dialect)
- Modify: `core/db.py` (engine swap)
- Modify: `config.py` (add `DATABASE_URL`, remove `DB_PATH`)
- Modify: `tests/conftest.py` (Postgres fixtures + truncate isolation)
- Modify: `pages/todos/models.py`, `pages/calendar/models.py`, `pages/friday/messages.py`, `pages/settings/routes.py` (`?`→`%s`, `lastrowid`→`RETURNING id`)

**Interfaces:**
- Consumes: nothing (foundation).
- Produces: `core.db.query(sql, params=(), *, one=False)`, `core.db.execute(sql, params=()) -> cursor` (committed; `.rowcount`, `.fetchone()` valid), `core.db.init_app(app)`, `core.db.init_db()`. `config.Config.DATABASE_URL: str`.

- [ ] **Step 1: Add psycopg to requirements**

Set `requirements.txt` to:

```
flask>=3.0
python-dotenv>=1.0
psycopg[binary]>=3.1
pytest>=8.0
```

Install: `pip install -r requirements.txt`

- [ ] **Step 2: Rewrite `schema.sql` for Postgres**

Replace the entire file with:

```sql
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS events (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title      TEXT    NOT NULL,
    start_at   TEXT    NOT NULL,
    end_at     TEXT,
    all_day    INTEGER NOT NULL DEFAULT 0,
    location   TEXT,
    notes      TEXT,
    created_at TEXT    NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS todos (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title        TEXT    NOT NULL,
    due_at       TEXT,
    done         INTEGER NOT NULL DEFAULT 0,
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS'),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role         TEXT NOT NULL,
    content      TEXT,
    tool_calls   TEXT,
    tool_call_id TEXT,
    name         TEXT,
    created_at   TEXT NOT NULL DEFAULT to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')
);
```

- [ ] **Step 3: Swap `core/db.py` to psycopg**

Replace the whole file with:

```python
"""Thin psycopg 3 layer. One connection per request via Flask's `g`."""
import psycopg
from psycopg.rows import dict_row
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def get_db() -> psycopg.Connection:
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if absent. Safe to call on every boot."""
    db = get_db()
    db.execute(SCHEMA.read_text(encoding="utf-8"))
    db.commit()


def query(sql: str, params=(), *, one: bool = False):
    rows = get_db().execute(sql, params).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, params=()):
    """Run a write and commit. Returns the committed cursor (for rowcount / RETURNING)."""
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
```

Note: `psycopg.Connection.execute(...)` returns a cursor, so `query` and `execute` bodies match the old shape. `init_db` runs the multi-statement schema in one `execute` call (psycopg accepts multiple `;`-separated statements in a simple query). The old `PRAGMA foreign_keys` line is dropped (SQLite-only).

- [ ] **Step 4: Update `config.py`**

Replace the `Config` class body's DB line. Remove `DB_PATH`, add `DATABASE_URL`:

```python
class Config:
    # Cloud (Spec A): Postgres via psycopg. Pooled Neon URL in prod.
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    HOST = os.environ.get("FRIDAY_HOST", "127.0.0.1")
    PORT = int(os.environ.get("FRIDAY_PORT", "5000"))
    # Phase 2 — DeepSeek. Missing key is not fatal; the agent emits a friendly error frame.
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
```

- [ ] **Step 5: Update `tests/conftest.py` to use Postgres**

Replace the file with:

```python
import os

import pytest

from app import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/friday_test"
)


@pytest.fixture
def app():
    # Real Postgres. Empty API key so the LLM is never reached, regardless of the dev's .env.
    app = create_app({"DATABASE_URL": TEST_DB_URL, "TESTING": True, "DEEPSEEK_API_KEY": ""})
    # Fresh state per test: create_app already ran init_db (CREATE IF NOT EXISTS); wipe rows + reset ids.
    with app.app_context():
        from core import db
        conn = db.get_db()
        conn.execute("TRUNCATE settings, events, todos, messages RESTART IDENTITY CASCADE")
        conn.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app):
    """App context for calling model functions directly."""
    with app.app_context():
        yield
```

- [ ] **Step 6: Port SQL in `pages/todos/models.py`**

Change every `?` to `%s`, and make `create_todo` read the new id via `RETURNING id`:

- `list_todos`: `sql += " WHERE done = %s"`
- `get_todo`: `query("SELECT * FROM todos WHERE id = %s", (todo_id,), one=True)`
- `create_todo` body (replace the `execute(...)` + `return`):

```python
    row = execute(
        "INSERT INTO todos (title, due_at, notes) VALUES (%s, %s, %s) RETURNING id",
        (title, due_at or None, data.get("notes") or None),
    ).fetchone()
    return get_todo(row["id"])
```

- `update_todo`: `"title = %s"`, `"due_at = %s"`, `"notes = %s"`, `"done = %s"`, `"completed_at = %s"`, and the final `execute(f"UPDATE todos SET {','.join(sets)} WHERE id = %s", params + [todo_id])`.
- `delete_todo`: `execute("DELETE FROM todos WHERE id = %s", (todo_id,)).rowcount > 0`

- [ ] **Step 7: Port SQL in `pages/calendar/models.py`**

- `list_events`: `where.append("start_at >= %s")` and `where.append("start_at <= %s")`.
- `get_event`: `query("SELECT * FROM events WHERE id = %s", (event_id,), one=True)`.
- `create_event` body (replace `execute(...)` + `return`):

```python
    row = execute(
        f"INSERT INTO events ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
        [fields[c] for c in cols],
    ).fetchone()
    return get_event(row["id"])
```

- `update_event`: `execute(f"UPDATE events SET {','.join(f'{c}=%s' for c in cols)} WHERE id = %s", [fields[c] for c in cols] + [event_id])`.
- `delete_event`: `execute("DELETE FROM events WHERE id = %s", (event_id,)).rowcount > 0`.

- [ ] **Step 8: Port SQL in `pages/friday/messages.py`**

`add()` INSERT placeholders:

```python
    execute(
        "INSERT INTO messages (role, content, tool_calls, tool_call_id, name) "
        "VALUES (%s, %s, %s, %s, %s)",
        (role, content, json.dumps(tool_calls) if tool_calls else None, tool_call_id, name),
    )
```

- [ ] **Step 9: Port SQL in `pages/settings/routes.py`**

`_set_pref` — placeholders and the Postgres timestamp expression:

```python
    execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
        (key, value),
    )
```

- [ ] **Step 10: Run the full suite against Postgres**

Run: `python -m pytest -q`
Expected: `34 passed`. If a test about `id` values fails, confirm `TRUNCATE ... RESTART IDENTITY` ran (ids restart at 1 per test).

- [ ] **Step 11: Commit**

```bash
git add requirements.txt schema.sql core/db.py config.py tests/conftest.py pages/todos/models.py pages/calendar/models.py pages/friday/messages.py pages/settings/routes.py
git commit -m "feat: port data layer from SQLite to Postgres (psycopg 3)"
```

---

## Task 2: Vercel serverless entrypoint

Deliverable: a WSGI entrypoint Vercel can serve, verified by an import smoke test.

**Files:**
- Create: `api/index.py`
- Create: `vercel.json`
- Create: `tests/test_wsgi.py`

**Interfaces:**
- Consumes: `app.create_app` (unchanged), `config.Config.DATABASE_URL` (Task 1).
- Produces: `api.index.app` (a Flask WSGI application).

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_wsgi.py`:

```python
import os

import tests.conftest as ct


def test_wsgi_entrypoint_exposes_flask_app(monkeypatch):
    # api/index.py calls create_app() with no overrides, so it reads DATABASE_URL from env.
    monkeypatch.setenv("DATABASE_URL", ct.TEST_DB_URL)
    from api.index import app
    assert callable(app.wsgi_app)          # it's a Flask/WSGI app
    assert "friday" in app.blueprints      # our blueprints are registered
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_wsgi.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`.

- [ ] **Step 3: Create the WSGI entrypoint**

Create `api/index.py`:

```python
"""Vercel serverless entrypoint. Exposes the Flask app as a WSGI callable named `app`."""
from app import create_app

app = create_app()
```

(No `api/__init__.py` needed for the import to resolve from the repo root; if the executor's layout requires it, add an empty one.)

- [ ] **Step 4: Create `vercel.json`**

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index" }],
  "functions": { "api/index.py": { "maxDuration": 60 } }
}
```

Every path (pages, `/api/*`, `/static/*`) routes to the Flask handler, which serves static assets itself — no CDN (design rule retained). `maxDuration: 60` is the Pro cap, set with Spec B (voice) in mind.

- [ ] **Step 5: Run the smoke test to verify it passes**

Run: `python -m pytest tests/test_wsgi.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/index.py vercel.json tests/test_wsgi.py
git commit -m "feat: add Vercel serverless WSGI entrypoint"
```

---

## Task 3: One-shot SQLite→Postgres migration script

Deliverable: a script that copies every row from a local `friday.db` into Postgres, with its row-copy core unit-tested. IDs are **reassigned** by Postgres (single user, no external references to ids — Spec A §6); timestamps are preserved.

**Files:**
- Create: `scripts/sqlite_to_pg.py`
- Create: `tests/test_migration.py`

**Interfaces:**
- Consumes: Postgres schema from Task 1 (`schema.sql`).
- Produces: `scripts.sqlite_to_pg.copy_rows(sqlite_conn, pg_conn)`, `scripts.sqlite_to_pg.TABLES` (dict: table name → tuple of columns copied, id omitted).

- [ ] **Step 1: Write the failing test**

Create `tests/test_migration.py`:

```python
import sqlite3

from scripts.sqlite_to_pg import TABLES, copy_rows


class FakeCursor:
    def __init__(self, sink): self.sink = sink
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=()): self.sink.append((sql, tuple(params)))


class FakePg:
    def __init__(self): self.calls = []; self.commits = 0
    def cursor(self): return FakeCursor(self.calls)
    def commit(self): self.commits += 1


def test_copy_rows_inserts_every_table_with_pg_placeholders():
    src = sqlite3.connect(":memory:")
    src.row_factory = sqlite3.Row
    src.executescript(
        "CREATE TABLE settings(key TEXT, value TEXT, updated_at TEXT);"
        "CREATE TABLE events(id INTEGER PRIMARY KEY, title TEXT, start_at TEXT, end_at TEXT,"
        " all_day INT, location TEXT, notes TEXT, created_at TEXT);"
        "CREATE TABLE todos(id INTEGER PRIMARY KEY, title TEXT, due_at TEXT, done INT,"
        " notes TEXT, created_at TEXT, completed_at TEXT);"
        "CREATE TABLE messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, tool_calls TEXT,"
        " tool_call_id TEXT, name TEXT, created_at TEXT);"
        "INSERT INTO settings VALUES('nav_collapsed','true','2026-07-23 10:00:00');"
        "INSERT INTO todos(title,due_at,done,notes,created_at,completed_at)"
        " VALUES('Buy milk',NULL,0,NULL,'2026-07-23 10:00:00',NULL);"
    )
    pg = FakePg()
    copy_rows(src, pg)

    sqls = [c[0] for c in pg.calls]
    # one insert per source row, all using %s, never ?
    assert any("INSERT INTO settings" in s for s in sqls)
    assert any("INSERT INTO todos" in s for s in sqls)
    assert all("?" not in s for s in sqls)
    assert all("%s" in s for s in sqls)
    # the todo row's title is carried through
    todo_call = next(c for c in pg.calls if "INTO todos" in c[0])
    assert "Buy milk" in todo_call[1]
    assert pg.commits >= 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_migration.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sqlite_to_pg'`.

- [ ] **Step 3: Write the migration script**

Create `scripts/sqlite_to_pg.py`:

```python
"""One-shot copy of a local friday.db (SQLite) into Postgres. Run once, locally.

Usage:
    DATABASE_URL=postgresql://... python -m scripts.sqlite_to_pg [path/to/friday.db]

IDs are reassigned by Postgres identity columns (single user, no external id refs).
Timestamps and all other values are preserved verbatim.
"""
import os
import sqlite3
import sys

import psycopg

# table -> columns copied (id omitted so Postgres identity assigns fresh ids)
TABLES = {
    "settings": ("key", "value", "updated_at"),
    "events": ("title", "start_at", "end_at", "all_day", "location", "notes", "created_at"),
    "todos": ("title", "due_at", "done", "notes", "created_at", "completed_at"),
    "messages": ("role", "content", "tool_calls", "tool_call_id", "name", "created_at"),
}


def copy_rows(sqlite_conn, pg_conn) -> None:
    for table, cols in TABLES.items():
        rows = sqlite_conn.execute(f"SELECT {','.join(cols)} FROM {table}").fetchall()
        collist = ",".join(cols)
        placeholders = ",".join(["%s"] * len(cols))
        with pg_conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    f"INSERT INTO {table} ({collist}) VALUES ({placeholders})",
                    tuple(row[c] for c in cols),
                )
        pg_conn.commit()
        print(f"  {table}: {len(rows)} rows")


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "friday.db"
    url = os.environ["DATABASE_URL"]
    src = sqlite3.connect(db_path)
    src.row_factory = sqlite3.Row
    with psycopg.connect(url) as pg:
        print(f"Copying {db_path} -> Postgres")
        copy_rows(src, pg)
    src.close()
    print("Done.")


if __name__ == "__main__":
    main()
```

Note: `row[c]` works because the SQLite connection uses `sqlite3.Row` (key access). `TABLES` column order matches `schema.sql`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_migration.py -q`
Expected: PASS.

- [ ] **Step 5: Document the manual run (no code)**

The real migration is run once by hand against the pre-migration `friday.db` (recover it from git history `b484299:friday.db` if already deleted from the tree, or a local copy):

```bash
DATABASE_URL="postgresql://...neon-pooled..." python -m scripts.sqlite_to_pg friday.db
```

- [ ] **Step 6: Commit**

```bash
git add scripts/sqlite_to_pg.py tests/test_migration.py
git commit -m "feat: add one-shot SQLite to Postgres migration script"
```

---

## Task 4: Config surface + identity docs

Deliverable: `.env.example` and `CLAUDE.md` reflect the Vercel/Postgres reality. No test (docs/config only).

**Files:**
- Modify: `.env.example`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `.env.example`**

Replace the DB/host lines so `DATABASE_URL` is documented and the SQLite path is gone:

```
# F.R.I.D.A.Y. — copy to .env.
# Data store (Spec A): Postgres via psycopg. Use the Neon POOLED connection string.
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
# Local dev run only (Flask dev server); ignored on Vercel:
FRIDAY_HOST=127.0.0.1
FRIDAY_PORT=5000

# Phase 2 — DeepSeek. Without a key, chat shows a friendly notice.
# DEEPSEEK_API_KEY=
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-chat

# Tests: a disposable Postgres (local Docker or a Neon branch).
# TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/friday_test
```

- [ ] **Step 2: Update `CLAUDE.md` Stack section**

Change the Stack paragraph so it describes the deployed reality. Replace the SQLite/`127.0.0.1` sentence with:

```
Flask app-factory + server-rendered Jinja + vanilla JS `fetch`, Postgres (Neon)
via psycopg 3. Deployed on Vercel serverless (`api/index.py` WSGI entrypoint);
secrets via Vercel env. No build step, no SPA. Single user. See
`docs/superpowers/specs/2026-07-23-cloud-migration-design.md`.
```

Leave the "Always" (RTK, ponytail) and "Design rules (hard)" sections unchanged — those still hold.

- [ ] **Step 3: Commit**

```bash
git add .env.example CLAUDE.md
git commit -m "docs: reflect Vercel + Postgres identity in config and CLAUDE.md"
```

---

## Self-Review

**Spec coverage** (Spec A §-by-§):
- §3 Runtime → Task 2 (`api/index.py`, `vercel.json`, `maxDuration`). ✓
- §4.1 Driver/connections → Task 1 Step 3 (psycopg, `dict_row`, per-request `g`). ✓ (Interface refined vs spec: `execute` returns a cursor, not a `returning=` kwarg — documented in Global Constraints.)
- §4.2 Schema dialect → Task 1 Step 2 (identity, `to_char` default). Open item "created_at strategy" resolved: SQL default via `to_char` (least model churn). ✓
- §4.3 SQL in models → Task 1 Steps 6–9 (`%s`, `RETURNING id`). ✓
- §5 Config → Task 1 Step 4 + Task 4 Step 1 (`DATABASE_URL`, drop `DB_PATH`). ✓
- §6 Migration → Task 3. Open item "preserve ids" resolved: reassign (ponytail). ✓
- §7 Testing → Task 1 Step 5 (real Postgres, truncate isolation). Open item "isolation mechanism" resolved: `TRUNCATE ... RESTART IDENTITY` per test. ✓
- §8 unchanged surface → no task touches routes/templates/agent. ✓
- §1 identity change / `CLAUDE.md` update → Task 4 Step 2. ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code. ✓

**Type consistency:** `execute(...)` returns a cursor everywhere; `.fetchone()["id"]` used in both `create_todo`/`create_event`; `.rowcount` in both deletes; `query(... one=True)` unchanged. `copy_rows(sqlite_conn, pg_conn)` and `TABLES` names match between Task 3 test and script. `api.index.app` matches Task 2 test import. ✓

All three §10 open items are resolved inline above.
