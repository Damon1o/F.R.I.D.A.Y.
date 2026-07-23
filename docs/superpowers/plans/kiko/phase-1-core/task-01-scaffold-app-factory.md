### Task 01: Project scaffold + config + app factory

First task in Phase 1. Stands up the empty repository into a runnable Flask app-factory
skeleton with config loading and the shared `ValidationError`, plus the pytest harness
every later task builds on. No database, no blueprints, no UI yet — just the shell and a
temporary `/healthz` route that later tasks replace.

**Context (global constraints that bind this task):**

- Python 3, Flask **app-factory** pattern. Server-rendered Jinja + vanilla JS later; **no
  build step, no frontend framework**.
- Persistence is **stdlib `sqlite3` only** (added in Task 02). This task does **not** add
  SQLAlchemy or any ORM. The prior build in git history (`bb6176f`) used Flask-SQLAlchemy —
  **do not reuse its `app.py`/`config.py`**; write fresh code matching the signatures below.
- Single user, **localhost**: server binds `127.0.0.1`. **No auth, no sessions/login.**
- Config comes from `.env` via `python-dotenv`; `config.py` reads it and scaffolds keys for
  later phases.
- All datetimes elsewhere are ISO-8601 UTC text (not relevant to this task; no dates here).
- **TDD**: write the failing test first, watch it fail, write minimal code, watch it pass,
  commit. Small frequent commits. DRY / YAGNI.

**Files:**

- **Create:**
  - `requirements.txt`
  - `.gitignore`
  - `.env.example`
  - `config.py`
  - `app.py`
  - `core/__init__.py`
  - `core/errors.py`
  - `pages/__init__.py`
  - `tests/__init__.py`
  - `tests/conftest.py`
- **Modify:** none
- **Test:** `tests/test_app.py`

**Interfaces:**

- **Consumes:** nothing (first task; no prior task output).
- **Produces (exact signatures — later tasks depend on these verbatim):**
  - `app.py` → `create_app(test_config: dict | None = None) -> Flask`
    - config keys: `DATABASE` (filesystem path or `':memory:'`), `SECRET_KEY`
    - registers blueprints and calls `db.init_app(app)` **in later tasks** (comment marker left here)
    - temporary `GET /healthz` route returns `('ok', 200)` until Task 08 replaces the index
  - `config.py` → module-level settings loaded from `.env`:
    `DATABASE` (default `'kiko.db'`), `SECRET_KEY` (default `'dev'`),
    `HOST = '127.0.0.1'`, `PORT` (default `5000`)
  - `core/errors.py` → `class ValidationError(Exception): pass`
    (raised by models on bad input; routes map it to HTTP 400)
  - `tests/conftest.py` → pytest `app` fixture (`create_app` with
    `{'DATABASE': ':memory:', 'TESTING': True}`) and `client` fixture

---

**STEPS**

- [ ] **Step 1: Create dependency, ignore, and env-example files.**
      These are static scaffolding (no test needed). Create the three files exactly as shown.

      `requirements.txt`:
      ```
      flask>=3.0
      python-dotenv>=1.0
      pytest>=8.0
      ```

      `.gitignore`:
      ```
      __pycache__/
      *.pyc
      .env
      kiko.db
      .venv/
      ```

      `.env.example` (copied to `.env` by the user; documents every key `config.py` reads —
      `SECRET_KEY`/`PORT` are scaffolded now so Phases 2–4 slot in without restructuring):
      ```
      # Kiko environment configuration.
      # Copy this file to `.env` and adjust as needed. `.env` is git-ignored.

      # SQLite database file path (or ":memory:" for an ephemeral in-memory DB).
      DATABASE=kiko.db

      # Flask secret key. Any random string; only used if sessions/flash are added later.
      SECRET_KEY=dev

      # Server bind port. Host is fixed to 127.0.0.1 (localhost-only, single user).
      PORT=5000
      ```

- [ ] **Step 2: Bootstrap the Python environment and confirm pytest runs.**
      Create an isolated virtualenv and install the pinned deps so the TDD loop can run.

      ```bash
      python -m venv .venv
      # Activate — POSIX:  source .venv/bin/activate
      # Activate — Windows (PowerShell):  .venv\Scripts\Activate.ps1
      python -m pip install --upgrade pip
      python -m pip install -r requirements.txt
      ```

      Sanity check (there are no tests yet, so pytest should report it collected nothing):
      ```bash
      python -m pytest -q
      ```
      **Expected output:** `no tests ran` (exit code 5). This only confirms pytest is installed.

      Commit the scaffolding (the venv is git-ignored and is **not** committed):
      ```bash
      git add requirements.txt .gitignore .env.example
      git commit -m "chore: scaffold dependencies, gitignore, and env example"
      ```

- [ ] **Step 3: Write the failing app-factory test + fixtures (RED).**
      Create the test package marker, the shared fixtures, and the tests. They import
      `app` and `core.errors`, which do not exist yet, so collection must fail.

      `tests/__init__.py` — empty file (makes `tests` a package so pytest prepends the repo
      root to `sys.path` and `import app` resolves):
      ```python
      ```

      `tests/conftest.py`:
      ```python
      import pytest

      from app import create_app


      @pytest.fixture
      def app():
          app = create_app({"DATABASE": ":memory:", "TESTING": True})
          yield app


      @pytest.fixture
      def client(app):
          return app.test_client()
      ```

      `tests/test_app.py`:
      ```python
      from flask import Flask

      from app import create_app
      from core.errors import ValidationError


      def test_create_app_returns_flask():
          app = create_app({"DATABASE": ":memory:", "TESTING": True})
          assert isinstance(app, Flask)


      def test_create_app_applies_test_config():
          app = create_app({"DATABASE": ":memory:", "TESTING": True})
          assert app.config["DATABASE"] == ":memory:"
          assert app.config["TESTING"] is True


      def test_create_app_uses_config_defaults_without_test_config():
          app = create_app()
          assert app.config["DATABASE"] == "kiko.db"
          assert app.config["HOST"] == "127.0.0.1"


      def test_healthz_returns_ok(client):
          response = client.get("/healthz")
          assert response.status_code == 200
          assert response.data == b"ok"


      def test_app_fixture_uses_in_memory_db(app):
          assert app.config["DATABASE"] == ":memory:"


      def test_validation_error_is_exception():
          assert issubclass(ValidationError, Exception)
      ```

      Run the test:
      ```bash
      python -m pytest tests/test_app.py -v
      ```
      **Expected: FAIL (collection error).** pytest cannot import `conftest.py`:
      ```
      ImportError while loading conftest '.../tests/conftest.py'.
      tests/conftest.py:3: in <module>
          from app import create_app
      E   ModuleNotFoundError: No module named 'app'
      ```
      Exit code is non-zero. This is the expected RED.

- [ ] **Step 4: Create `config.py` (loads `.env`, exposes settings).**
      Module-level UPPERCASE constants so `app.config.from_object(config)` picks them up.
      `HOST` is a fixed constant (localhost-only); `DATABASE`, `SECRET_KEY`, `PORT` come from
      the environment with defaults.

      `config.py`:
      ```python
      import os

      from dotenv import load_dotenv

      # Load key=value pairs from a local .env file into os.environ (no-op if absent).
      load_dotenv()

      # SQLite database file path, or ":memory:" for an ephemeral in-memory database.
      DATABASE = os.environ.get("DATABASE", "kiko.db")

      # Flask secret key. Defaults to "dev" for local use; override in .env if needed.
      SECRET_KEY = os.environ.get("SECRET_KEY", "dev")

      # Bind host is fixed to localhost — single-user personal app, no auth.
      HOST = "127.0.0.1"

      # Server port (integer).
      PORT = int(os.environ.get("PORT", "5000"))
      ```

- [ ] **Step 5: Create the `core` package and `ValidationError`.**
      `core/__init__.py` — empty file (package marker):
      ```python
      ```

      `core/errors.py`:
      ```python
      class ValidationError(Exception):
          """Raised by models on invalid input. Routes catch it and return HTTP 400."""
          pass
      ```

- [ ] **Step 6: Create the `pages` package marker.**
      `pages/__init__.py` — empty file (package marker; blueprints land here in Tasks 04–08):
      ```python
      ```

- [ ] **Step 7: Create `app.py` (the factory) and turn the suite GREEN.**
      Applies `config.py` defaults, then overlays `test_config`, registers the temporary
      `/healthz` route, and leaves an explicit marker where Task 02 adds `db.init_app(app)`
      and Tasks 04–08 register blueprints.

      `app.py`:
      ```python
      from flask import Flask

      import config


      def create_app(test_config: dict | None = None) -> Flask:
          """Application factory.

          Args:
              test_config: optional dict of config overrides (e.g.
                  {"DATABASE": ":memory:", "TESTING": True}). Applied on top of the
                  defaults loaded from config.py / .env.
          """
          app = Flask(__name__)

          # Load DATABASE, SECRET_KEY, HOST, PORT from config.py (which read .env).
          app.config.from_object(config)

          # Test overrides win over defaults.
          if test_config:
              app.config.update(test_config)

          # --- Added by later tasks (do not implement here) ---
          # Task 02 — database wiring:
          #   from core import db
          #   db.init_app(app)
          # Tasks 04-08 — blueprints:
          #   from pages.calendar.routes import calendar_bp
          #   app.register_blueprint(calendar_bp)
          #   from pages.todos.routes import todos_bp
          #   app.register_blueprint(todos_bp)
          #   from pages.dashboard.routes import dashboard_bp
          #   app.register_blueprint(dashboard_bp)
          # ----------------------------------------------------

          # Temporary liveness route. Task 08's dashboard blueprint owns "/"; this
          # /healthz endpoint stays as a trivial readiness check.
          @app.route("/healthz")
          def healthz():
              return "ok", 200

          return app


      if __name__ == "__main__":
          # Direct run: `python app.py`. `flask run` also works (Flask auto-detects the
          # create_app factory in app.py). Bind localhost only.
          create_app().run(host=config.HOST, port=config.PORT, debug=True)
      ```

      Run the suite:
      ```bash
      python -m pytest tests/test_app.py -v
      ```
      **Expected: PASS** — 6 passed. Each test green:
      `test_create_app_returns_flask`, `test_create_app_applies_test_config`,
      `test_create_app_uses_config_defaults_without_test_config`,
      `test_healthz_returns_ok`, `test_app_fixture_uses_in_memory_db`,
      `test_validation_error_is_exception`.

- [ ] **Step 8: Full-suite green check and commit.**
      Confirm the whole (currently single-file) suite is green:
      ```bash
      python -m pytest -v
      ```
      **Expected:** `6 passed`.

      Commit the app factory, config, error type, package markers, and tests:
      ```bash
      git add app.py config.py core/__init__.py core/errors.py pages/__init__.py \
              tests/__init__.py tests/conftest.py tests/test_app.py
      git commit -m "feat: add app factory, config, and ValidationError with passing tests"
      ```

- [ ] **Step 9 (optional smoke): confirm the app boots for a human.**
      Not required for the suite, but verifies `flask run` discovery works before handing off:
      ```bash
      python app.py
      # then, in another shell:  curl http://127.0.0.1:5000/healthz  ->  ok
      # Ctrl-C to stop.
      ```
      Nothing to commit here.

---

**Done when:** `python -m pytest -v` reports `6 passed`; `create_app()` returns a `Flask`
instance; `GET /healthz` returns `200` with body `ok`; `config.py` exposes
`DATABASE`/`SECRET_KEY`/`HOST`/`PORT`; `core.errors.ValidationError` exists; and
`tests/conftest.py` provides `app` + `client` fixtures on an in-memory database. Task 02
consumes this by implementing `core/db.py` and uncommenting the `db.init_app(app)` marker.
