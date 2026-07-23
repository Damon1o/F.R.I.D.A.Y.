### Task 02: SQLite DB layer + schema

Build the single shared data dependency for Kiko: the SQLite schema (`schema.sql`)
and the thin stdlib-`sqlite3` access layer (`core/db.py`), then wire it into the app
factory so tables exist on startup. Every later page (calendar, todos, dashboard)
talks to the database only through the four helpers produced here.

**Constraints that govern this task** (from the Phase 1 contract):

- Python 3, Flask **app-factory** pattern. NO build step, NO ORM.
- Persistence: **stdlib `sqlite3` ONLY** — no SQLAlchemy. Schema lives in `schema.sql`;
  all helpers live in `core/db.py`.
- Single user, localhost. No auth, no sessions.
- Datetimes are stored as **ISO-8601 UTC text** (the schema columns are `TEXT`).
- **TDD**: write the failing test, run it and watch it fail, write the minimal code,
  run it and watch it pass, commit. Small frequent commits.
- DRY / YAGNI: only the five contract functions, nothing speculative.

**Recovered files:** none. The prior `core/db.py` at `bb6176f` was a two-line
`flask_sqlalchemy` shim (`db = SQLAlchemy()`) and is **incompatible** with the
stdlib-`sqlite3`-only rule, so it is NOT reused. There was no `schema.sql` in history.
Both files in this task are authored fresh; `schema.sql` is copied verbatim from the
approved design spec §4.

---

**Files:**

- **Create:** `schema.sql` — verbatim `events` + `todos` `CREATE TABLE` statements from
  spec §4.
- **Create:** `core/db.py` — `get_db`, `close_db`, `init_db`, `query`, `execute`,
  `init_app`.
- **Modify:** `app.py` — import `core.db` and call `db.init_app(app)` inside `create_app`.
- **Test:** `tests/test_db.py` — app-context + in-memory / temp-file SQLite tests.

**Interfaces:**

- **Consumes** (from Task 01):
  - `create_app(test_config: dict | None = None) -> Flask` — config keys `DATABASE`
    (a filesystem path or `':memory:'`) and `SECRET_KEY`. `core/__init__.py` already
    exists (Task 01 created `core/errors.py`), so `core` is an importable package.
- **Produces** (must match the global contract EXACTLY):
  - `init_app(app) -> None` — registers the `close_db` teardown and ensures tables exist.
  - `get_db() -> sqlite3.Connection` — `row_factory = sqlite3.Row`; cached on `flask.g`.
  - `query(sql: str, params: tuple = ()) -> list[sqlite3.Row]`
  - `execute(sql: str, params: tuple = ()) -> int` — returns `lastrowid`; commits.
  - `init_db() -> None` — runs `schema.sql`.
  - `schema.sql` defines tables `events` and `todos`.
  - (`close_db(e=None) -> None` is an internal teardown helper, not part of the public
    contract, but is defined here.)

---

- [ ] **Step 1: Verify Task 01 prerequisites exist.**
  This task builds on Task 01. Confirm the app factory, config, and `core` package are
  present before starting. Run:

  ```bash
  python -c "import app, config; import core; from app import create_app; print('ok')"
  ```

  Expected output: `ok`. If this fails, Task 01 is not complete — stop and finish it
  first. (`core/__init__.py` must exist because Task 01 created `core/errors.py`.)

- [ ] **Step 2: Write the failing DB-helper test.**
  Create `tests/test_db.py` with the four core behaviors from the test focus:
  `get_db` returns the same connection within one app context; `init_db` creates the
  `events` and `todos` tables; `execute` INSERT returns a `lastrowid`; `query`
  round-trips a row. All four run inside a single `app.app_context()` against an
  in-memory database (which is why they call `init_db()` themselves — a fresh
  `:memory:` connection starts empty).

  ```python
  import pytest

  from app import create_app
  from core import db


  @pytest.fixture
  def app():
      return create_app({"DATABASE": ":memory:", "SECRET_KEY": "test"})


  def test_get_db_returns_same_conn_within_context(app):
      with app.app_context():
          assert db.get_db() is db.get_db()


  def test_init_db_creates_events_and_todos_tables(app):
      with app.app_context():
          db.init_db()
          names = {
              row["name"]
              for row in db.query(
                  "SELECT name FROM sqlite_master WHERE type = 'table'"
              )
          }
      assert "events" in names
      assert "todos" in names


  def test_execute_insert_returns_lastrowid(app):
      with app.app_context():
          db.init_db()
          rowid = db.execute("INSERT INTO todos (title) VALUES (?)", ("ship it",))
      assert isinstance(rowid, int)
      assert rowid == 1


  def test_query_round_trips_a_row(app):
      with app.app_context():
          db.init_db()
          db.execute(
              "INSERT INTO events (title, start_at) VALUES (?, ?)",
              ("standup", "2026-07-22T09:00:00Z"),
          )
          rows = db.query("SELECT title, start_at FROM events")
      assert len(rows) == 1
      assert rows[0]["title"] == "standup"
      assert rows[0]["start_at"] == "2026-07-22T09:00:00Z"
  ```

- [ ] **Step 3: Run the test — expect FAIL (no `core.db` module).**

  ```bash
  python -m pytest tests/test_db.py -v
  ```

  Expected: a collection error because `core/db.py` does not exist yet —
  `ModuleNotFoundError: No module named 'core.db'`
  (pytest reports `ERROR tests/test_db.py`, 0 tests run).

- [ ] **Step 4: Create `schema.sql` (verbatim from spec §4).**
  Copy the `events` + `todos` table definitions exactly as approved. Datetimes are
  `TEXT` (ISO-8601 UTC); booleans are `INTEGER` 0/1; `created_at` defaults to
  `datetime('now')` (UTC).

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

- [ ] **Step 5: Create `core/db.py` (the full access layer).**
  `get_db` opens one `sqlite3` connection per app context, caches it on `flask.g`, and
  sets `row_factory = sqlite3.Row` so rows are dict-like. `init_db` reads `schema.sql`
  via `current_app.open_resource` (which resolves relative to the app root, i.e. the
  project directory containing `app.py` and `schema.sql`) and runs it with
  `executescript`. `execute` commits and returns `lastrowid`; `query` returns
  `fetchall()`. `init_app` registers the teardown and, so a real file database has its
  tables on first boot, runs `init_db()` once inside an app context (the schema uses
  `CREATE TABLE IF NOT EXISTS`, so this is idempotent).

  ```python
  import sqlite3

  from flask import current_app, g


  def get_db() -> sqlite3.Connection:
      if "db" not in g:
          g.db = sqlite3.connect(current_app.config["DATABASE"])
          g.db.row_factory = sqlite3.Row
      return g.db


  def close_db(e=None) -> None:
      db = g.pop("db", None)
      if db is not None:
          db.close()


  def init_db() -> None:
      db = get_db()
      with current_app.open_resource("schema.sql") as f:
          db.executescript(f.read().decode("utf-8"))
      db.commit()


  def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
      return get_db().execute(sql, params).fetchall()


  def execute(sql: str, params: tuple = ()) -> int:
      db = get_db()
      cursor = db.execute(sql, params)
      db.commit()
      return cursor.lastrowid


  def init_app(app) -> None:
      app.teardown_appcontext(close_db)
      with app.app_context():
          init_db()
  ```

- [ ] **Step 6: Run the test — expect PASS (4 passed).**
  The four tests call `init_db()` themselves and never rely on the app factory yet, so
  they go green as soon as `schema.sql` + `core/db.py` exist.

  ```bash
  python -m pytest tests/test_db.py -v
  ```

  Expected: `4 passed`.

- [ ] **Step 7: Commit the schema and access layer.**

  ```bash
  git add schema.sql core/db.py tests/test_db.py
  git commit -m "feat(db): add sqlite schema and core.db access helpers"
  ```

- [ ] **Step 8: Add the failing boot-wiring test.**
  Append one more test to `tests/test_db.py` proving the app factory itself creates the
  tables on startup. It uses a real temp-file database (via pytest's `tmp_path`) so the
  boot-time `init_db()` persists and a fresh connection can see the tables. This will
  fail until `app.py` calls `db.init_app(app)`.

  ```python
  def test_init_app_creates_tables_on_boot(tmp_path):
      db_path = tmp_path / "kiko.db"
      application = create_app({"DATABASE": str(db_path), "SECRET_KEY": "test"})
      with application.app_context():
          names = {
              row["name"]
              for row in db.query(
                  "SELECT name FROM sqlite_master WHERE type = 'table'"
              )
          }
      assert "events" in names
      assert "todos" in names
  ```

- [ ] **Step 9: Run the test — expect FAIL (factory not wired).**

  ```bash
  python -m pytest tests/test_db.py::test_init_app_creates_tables_on_boot -v
  ```

  Expected: `FAILED tests/test_db.py::test_init_app_creates_tables_on_boot` —
  `AssertionError: assert 'events' in set()` (the file database is empty because
  `create_app` does not call `init_app` yet).

- [ ] **Step 10: Wire `db.init_app(app)` into `create_app`.**
  Open `app.py`. After Task 01 it looks like the "before" below (the exact whitespace
  around blueprint stubs / the `/healthz` route may differ in your Task 01 output —
  match the two anchors, not the surrounding lines). Make exactly two additions: the
  `from core import db` import, and the `db.init_app(app)` call placed **after** the
  config is applied (so `DATABASE` is set before `init_db` reads it) and before the
  routes/return.

  **Before (Task 01 baseline):**

  ```python
  from flask import Flask

  import config


  def create_app(test_config: dict | None = None) -> Flask:
      app = Flask(__name__)
      app.config.from_mapping(
          DATABASE=config.DATABASE,
          SECRET_KEY=config.SECRET_KEY,
      )
      if test_config is not None:
          app.config.update(test_config)

      @app.route("/healthz")
      def healthz():
          return "ok", 200

      return app
  ```

  **After (this task):**

  ```python
  from flask import Flask

  import config
  from core import db


  def create_app(test_config: dict | None = None) -> Flask:
      app = Flask(__name__)
      app.config.from_mapping(
          DATABASE=config.DATABASE,
          SECRET_KEY=config.SECRET_KEY,
      )
      if test_config is not None:
          app.config.update(test_config)

      db.init_app(app)

      @app.route("/healthz")
      def healthz():
          return "ok", 200

      return app
  ```

  Apply it as two exact edits:
  - Edit 1 — add the import. Replace:
    ```python
    import config
    ```
    with:
    ```python
    import config
    from core import db
    ```
  - Edit 2 — add the call. Replace:
    ```python
        if test_config is not None:
            app.config.update(test_config)
    ```
    with:
    ```python
        if test_config is not None:
            app.config.update(test_config)

        db.init_app(app)
    ```

- [ ] **Step 11: Run the full DB test file — expect PASS (5 passed).**

  ```bash
  python -m pytest tests/test_db.py -v
  ```

  Expected: `5 passed`. (The four in-memory tests still pass — the boot-time
  `init_db()` for `':memory:'` builds a throwaway database and is harmless; each app
  context gets its own in-memory connection.)

- [ ] **Step 12: Run the whole suite to confirm no regression.**
  Confirm Task 01's `/healthz` and any other existing tests still pass now that the
  factory initializes the database on boot.

  ```bash
  python -m pytest -v
  ```

  Expected: all tests pass (Task 01 tests + the 5 new DB tests).

- [ ] **Step 13: Commit the factory wiring.**

  ```bash
  git add app.py tests/test_db.py
  git commit -m "feat(db): initialize database schema on app startup"
  ```
