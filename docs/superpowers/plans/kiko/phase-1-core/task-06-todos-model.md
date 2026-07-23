### Task 06: Todos model (CRUD + validation + completed_at)

Implements `pages/todos/models.py` — the persistence + validation layer for the To-Do
page. Uses stdlib `sqlite3` through the shared `core.db` helpers (Task 02) and raises
`core.errors.ValidationError` (Task 01) on bad input. No ORM, no SQLAlchemy.

Datetimes are stored as ISO-8601 UTC text (per `schema.sql`). The `done` column is a
`0/1` integer exposed to callers as a Python `bool`. `completed_at` is set to the current
UTC time when `done` flips `0 -> 1` and cleared to `NULL` when it flips `1 -> 0`.

> **No file is recovered from git history for this task.** The prior
> `pages/calendar/models.py` at `bb6176f` was a SQLAlchemy `db.Model`; the Phase 1 design
> replaces that with stdlib `sqlite3`. This module is written fresh against `core.db`.

**Files:**

- **Create:** `pages/todos/__init__.py` (empty package marker)
- **Create:** `pages/todos/models.py`
- **Modify:** none
- **Test:** `tests/test_todos_model.py`

**Interfaces:**

_Consumes:_

```python
# core/db.py (Task 02)
query(sql: str, params: tuple = ()) -> list[sqlite3.Row]   # row_factory = sqlite3.Row
execute(sql: str, params: tuple = ()) -> int               # returns lastrowid; commits

# core/errors.py (Task 01)
class ValidationError(Exception): pass                      # routes map to HTTP 400
```

_Produces (must match the global contract EXACTLY):_

```python
# pages/todos/models.py (Task 06)
create_todo(data: dict) -> dict            # keys: title(req), due_at?, notes?
get_todo(todo_id: int) -> dict | None
list_todos(done: bool | None = None) -> list[dict]
update_todo(todo_id: int, data: dict) -> dict | None   # toggling done sets/clears completed_at
delete_todo(todo_id: int) -> bool
# returned dicts include: id, title, due_at, done (bool), notes, created_at, completed_at
```

**Schema this module targets** (owned by Task 02 `schema.sql`; shown for reference only —
do **not** edit `schema.sql` in this task):

```sql
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

**Test-fixture prerequisite (from Task 02 `tests/conftest.py`):** the tests below take the
`app` fixture. That fixture must build the Flask app with an in-memory database, run
`init_db()` (which applies `schema.sql`, creating the `todos` table), and **`yield` inside
an active application context** — the standard pattern required for `:memory:` SQLite so
that `core.db.get_db()`'s single cached connection is shared across `init_db()` and every
model call in the test. The reference shape:

```python
# tests/conftest.py  (Task 02 — already exists before this task runs; do NOT create it here)
import pytest
from app import create_app
from core.db import init_db

@pytest.fixture
def app():
    app = create_app({"DATABASE": ":memory:", "SECRET_KEY": "test"})
    with app.app_context():
        init_db()
        yield app          # context stays active for the whole test
```

The model functions call `core.db` helpers that read `flask.g`, so every test body runs
inside this active context. Tests use **local imports** of `pages.todos.models` so each
step's RED failure is isolated to the functions that step introduces.

---

- [ ] **Step 1: Confirm prerequisites (no code)**
  - Verify Task 01 (`core/errors.py` with `ValidationError`), Task 02 (`core/db.py` with
    `query`/`execute`/`init_db` + `tests/conftest.py` `app` fixture and `schema.sql`
    containing the `todos` table) are merged and importable. Quick check:
    ```bash
    python -c "from core.errors import ValidationError; from core.db import query, execute; print('ok')"
    ```
    Expected: prints `ok`. If this fails, stop — Tasks 01/02 are not yet in place.

- [ ] **Step 2: create_todo + get_todo (happy path)**
  - Write the failing test. Create `tests/test_todos_model.py`:
    ```python
    import pytest


    def test_create_todo_returns_dict(app):
        from pages.todos.models import create_todo

        todo = create_todo({"title": "Buy milk"})

        assert isinstance(todo["id"], int) and todo["id"] > 0
        assert todo["title"] == "Buy milk"
        assert todo["due_at"] is None
        assert todo["notes"] is None
        assert todo["done"] is False
        assert todo["completed_at"] is None
        assert todo["created_at"]  # populated by the DB default


    def test_create_todo_persists_optional_fields(app):
        from pages.todos.models import create_todo, get_todo

        created = create_todo(
            {"title": "Call bank", "due_at": "2026-07-25T09:00:00", "notes": "acct 12"}
        )

        assert created["due_at"] == "2026-07-25T09:00:00"
        assert created["notes"] == "acct 12"
        assert get_todo(created["id"]) == created


    def test_get_todo_missing_returns_none(app):
        from pages.todos.models import get_todo

        assert get_todo(9999) is None
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: errors/fails with `ModuleNotFoundError: No module named 'pages.todos'`
    (the package and module do not exist yet).
  - Minimal implementation. Create the empty package marker `pages/todos/__init__.py`:
    ```python
    ```
    (leave the file empty). Then create `pages/todos/models.py`:
    ```python
    """Todo persistence for the Kiko to-do page: CRUD + validation."""

    from core.db import execute, query


    def _row_to_dict(row) -> dict:
        """Convert a todos sqlite3.Row into a plain dict (done as bool)."""
        return {
            "id": row["id"],
            "title": row["title"],
            "due_at": row["due_at"],
            "done": bool(row["done"]),
            "notes": row["notes"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }


    def create_todo(data: dict) -> dict:
        """Insert a todo and return it as a dict."""
        todo_id = execute(
            "INSERT INTO todos (title, due_at, notes) VALUES (?, ?, ?)",
            (data.get("title"), data.get("due_at"), data.get("notes")),
        )
        return get_todo(todo_id)


    def get_todo(todo_id: int) -> dict | None:
        """Return a single todo dict, or None if the id does not exist."""
        rows = query("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return _row_to_dict(rows[0]) if rows else None
    ```
  - Run it, expected PASS:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `3 passed`.
  - Commit:
    ```bash
    git add pages/todos/__init__.py pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): add create_todo and get_todo model functions"
    ```

- [ ] **Step 3: Validation — title required, due_at ISO-8601**
  - Write the failing tests. Append to `tests/test_todos_model.py`:
    ```python
    def test_create_todo_empty_title_raises(app):
        from core.errors import ValidationError
        from pages.todos.models import create_todo

        for bad in ("", "   ", None):
            with pytest.raises(ValidationError):
                create_todo({"title": bad})


    def test_create_todo_missing_title_raises(app):
        from core.errors import ValidationError
        from pages.todos.models import create_todo

        with pytest.raises(ValidationError):
            create_todo({})


    def test_create_todo_strips_title(app):
        from pages.todos.models import create_todo

        todo = create_todo({"title": "  Walk dog  "})

        assert todo["title"] == "Walk dog"


    def test_create_todo_bad_due_at_raises(app):
        from core.errors import ValidationError
        from pages.todos.models import create_todo

        with pytest.raises(ValidationError):
            create_todo({"title": "x", "due_at": "not-a-date"})


    def test_create_todo_valid_due_at_accepted(app):
        from pages.todos.models import create_todo

        todo = create_todo({"title": "x", "due_at": "2026-08-01"})

        assert todo["due_at"] == "2026-08-01"
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -k "title or due_at" -q
    ```
    Expected: failures such as `Failed: DID NOT RAISE <class 'core.errors.ValidationError'>`
    (empty/missing title and bad due_at are not validated yet) and an `AssertionError` on
    `test_create_todo_strips_title` (`'  Walk dog  ' != 'Walk dog'`).
  - Minimal implementation. Replace the entire contents of `pages/todos/models.py` with:
    ```python
    """Todo persistence for the Kiko to-do page: CRUD + validation.

    Datetimes are stored as ISO-8601 UTC text (see schema.sql). The ``done``
    column is a 0/1 integer exposed to callers as a Python bool.
    """

    from datetime import datetime

    from core.db import execute, query
    from core.errors import ValidationError


    def _clean_title(value: object) -> str:
        """Return a stripped, non-empty title, or raise ValidationError."""
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("title is required")
        return value.strip()


    def _clean_due_at(value: object) -> str | None:
        """Validate an optional ISO-8601 due date; return it unchanged (or None)."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValidationError("due_at must be an ISO-8601 datetime")
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValidationError("due_at must be an ISO-8601 datetime")
        return value


    def _row_to_dict(row) -> dict:
        """Convert a todos sqlite3.Row into a plain dict (done as bool)."""
        return {
            "id": row["id"],
            "title": row["title"],
            "due_at": row["due_at"],
            "done": bool(row["done"]),
            "notes": row["notes"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }


    def create_todo(data: dict) -> dict:
        """Insert a todo. Requires a non-empty title; due_at optional ISO-8601."""
        title = _clean_title(data.get("title"))
        due_at = _clean_due_at(data.get("due_at"))
        todo_id = execute(
            "INSERT INTO todos (title, due_at, notes) VALUES (?, ?, ?)",
            (title, due_at, data.get("notes")),
        )
        return get_todo(todo_id)


    def get_todo(todo_id: int) -> dict | None:
        """Return a single todo dict, or None if the id does not exist."""
        rows = query("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return _row_to_dict(rows[0]) if rows else None
    ```
  - Run it, expected PASS:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `8 passed`.
  - Commit:
    ```bash
    git add pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): validate title and due_at in create_todo"
    ```

- [ ] **Step 4: update_todo — field patching + missing id**
  - Write the failing tests. Append to `tests/test_todos_model.py`:
    ```python
    def test_update_todo_patches_fields(app):
        from pages.todos.models import create_todo, update_todo

        todo = create_todo({"title": "Old", "notes": "a"})
        updated = update_todo(
            todo["id"], {"title": "New", "notes": "b", "due_at": "2026-09-01T08:00:00"}
        )

        assert updated["title"] == "New"
        assert updated["notes"] == "b"
        assert updated["due_at"] == "2026-09-01T08:00:00"
        assert updated["done"] is False
        assert updated["completed_at"] is None


    def test_update_todo_validates_title(app):
        from core.errors import ValidationError
        from pages.todos.models import create_todo, update_todo

        todo = create_todo({"title": "Old"})
        with pytest.raises(ValidationError):
            update_todo(todo["id"], {"title": "   "})


    def test_update_todo_can_clear_due_at(app):
        from pages.todos.models import create_todo, update_todo

        todo = create_todo({"title": "x", "due_at": "2026-09-01T08:00:00"})
        updated = update_todo(todo["id"], {"due_at": None})

        assert updated["due_at"] is None


    def test_update_todo_missing_returns_none(app):
        from pages.todos.models import update_todo

        assert update_todo(9999, {"title": "x"}) is None
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -k update -q
    ```
    Expected: `ImportError: cannot import name 'update_todo' from 'pages.todos.models'`.
  - Minimal implementation. Add the following `update_todo` function to
    `pages/todos/models.py`, immediately after `get_todo` (do not touch the existing
    functions):
    ```python
    def update_todo(todo_id: int, data: dict) -> dict | None:
        """Patch a todo's fields. Returns the updated dict, or None if missing."""
        current = get_todo(todo_id)
        if current is None:
            return None

        fields: dict = {}
        if "title" in data:
            fields["title"] = _clean_title(data.get("title"))
        if "due_at" in data:
            fields["due_at"] = _clean_due_at(data.get("due_at"))
        if "notes" in data:
            fields["notes"] = data.get("notes")

        if fields:
            assignments = ", ".join(f"{col} = ?" for col in fields)
            params = tuple(fields.values()) + (todo_id,)
            execute(f"UPDATE todos SET {assignments} WHERE id = ?", params)

        return get_todo(todo_id)
    ```
    (The `{col}` names come only from the fixed key set above, never from user data, so
    the f-string builds no injectable SQL; all values are passed as `?` parameters.)
  - Run it, expected PASS:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `12 passed`.
  - Commit:
    ```bash
    git add pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): add update_todo field patching"
    ```

- [ ] **Step 5: update_todo — done toggle sets/clears completed_at**
  - Write the failing tests. Append to `tests/test_todos_model.py`:
    ```python
    def test_toggle_done_sets_then_clears_completed_at(app):
        from datetime import datetime

        from pages.todos.models import create_todo, update_todo

        todo = create_todo({"title": "x"})

        done = update_todo(todo["id"], {"done": True})
        assert done["done"] is True
        assert done["completed_at"] is not None
        datetime.fromisoformat(done["completed_at"])  # must be valid ISO-8601

        reopened = update_todo(todo["id"], {"done": False})
        assert reopened["done"] is False
        assert reopened["completed_at"] is None


    def test_toggle_done_idempotent_keeps_completed_at(app):
        from pages.todos.models import create_todo, update_todo

        todo = create_todo({"title": "x"})
        first = update_todo(todo["id"], {"done": True})
        again = update_todo(todo["id"], {"done": True})

        assert again["completed_at"] == first["completed_at"]
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -k done -q
    ```
    Expected: `AssertionError` on `assert done["done"] is True` — the current
    `update_todo` ignores the `done` key entirely, so the row is never marked done.
  - Minimal implementation. (a) Change the datetime import at the top of
    `pages/todos/models.py` from:
    ```python
    from datetime import datetime
    ```
    to:
    ```python
    from datetime import datetime, timezone
    ```
    (b) Add this helper directly below the imports (above `_clean_title`):
    ```python
    def _utc_now_iso() -> str:
        """Current UTC time as ISO-8601 text, seconds precision."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ```
    (c) In `update_todo`, add the `done` handling block after the `notes` block and
    before the `if fields:` block, so the field-collecting section reads exactly:
    ```python
        fields: dict = {}
        if "title" in data:
            fields["title"] = _clean_title(data.get("title"))
        if "due_at" in data:
            fields["due_at"] = _clean_due_at(data.get("due_at"))
        if "notes" in data:
            fields["notes"] = data.get("notes")
        if "done" in data:
            new_done = bool(data.get("done"))
            fields["done"] = 1 if new_done else 0
            if new_done and not current["done"]:
                fields["completed_at"] = _utc_now_iso()
            elif not new_done and current["done"]:
                fields["completed_at"] = None
    ```
  - Run it, expected PASS:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `14 passed`.
  - Commit:
    ```bash
    git add pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): set/clear completed_at on done toggle"
    ```

- [ ] **Step 6: list_todos — all + done filter (excludes completed)**
  - Write the failing tests. Append to `tests/test_todos_model.py`:
    ```python
    def test_list_todos_returns_all_in_order(app):
        from pages.todos.models import create_todo, list_todos

        create_todo({"title": "A"})
        create_todo({"title": "B"})

        assert [t["title"] for t in list_todos()] == ["A", "B"]


    def test_list_todos_done_filter_excludes_completed(app):
        from pages.todos.models import create_todo, list_todos, update_todo

        create_todo({"title": "A"})
        b = create_todo({"title": "B"})
        update_todo(b["id"], {"done": True})

        assert [t["title"] for t in list_todos(done=False)] == ["A"]
        assert [t["title"] for t in list_todos(done=True)] == ["B"]
        assert len(list_todos()) == 2
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -k list -q
    ```
    Expected: `ImportError: cannot import name 'list_todos' from 'pages.todos.models'`.
  - Minimal implementation. Add the following `list_todos` function to
    `pages/todos/models.py`, immediately after `get_todo`:
    ```python
    def list_todos(done: bool | None = None) -> list[dict]:
        """List todos in creation order, optionally filtered by done state."""
        if done is None:
            rows = query("SELECT * FROM todos ORDER BY id")
        else:
            rows = query(
                "SELECT * FROM todos WHERE done = ? ORDER BY id",
                (1 if done else 0,),
            )
        return [_row_to_dict(row) for row in rows]
    ```
  - Run it, expected PASS:
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `16 passed`.
  - Commit:
    ```bash
    git add pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): add list_todos with done filter"
    ```

- [ ] **Step 7: delete_todo + missing id**
  - Write the failing tests. Append to `tests/test_todos_model.py`:
    ```python
    def test_delete_todo_removes_row(app):
        from pages.todos.models import create_todo, delete_todo, get_todo

        todo = create_todo({"title": "x"})

        assert delete_todo(todo["id"]) is True
        assert get_todo(todo["id"]) is None


    def test_delete_todo_missing_returns_false(app):
        from pages.todos.models import delete_todo

        assert delete_todo(9999) is False
    ```
  - Run it, expected FAIL:
    ```bash
    python -m pytest tests/test_todos_model.py -k delete -q
    ```
    Expected: `ImportError: cannot import name 'delete_todo' from 'pages.todos.models'`.
  - Minimal implementation. Add the following `delete_todo` function to the end of
    `pages/todos/models.py`:
    ```python
    def delete_todo(todo_id: int) -> bool:
        """Delete a todo. Return True if a row was removed, else False."""
        if get_todo(todo_id) is None:
            return False
        execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        return True
    ```
  - Run it, expected PASS (full file — this is the complete model):
    ```bash
    python -m pytest tests/test_todos_model.py -q
    ```
    Expected: `18 passed`.
  - **Final `pages/todos/models.py` should now read exactly as below** (use this to verify
    the assembled file):
    ```python
    """Todo persistence for the Kiko to-do page: CRUD + validation.

    Datetimes are stored as ISO-8601 UTC text (see schema.sql). The ``done``
    column is a 0/1 integer exposed to callers as a Python bool. ``completed_at``
    is set to the current UTC time when ``done`` flips 0 -> 1 and cleared to NULL
    when it flips 1 -> 0.
    """

    from datetime import datetime, timezone

    from core.db import execute, query
    from core.errors import ValidationError


    def _utc_now_iso() -> str:
        """Current UTC time as ISO-8601 text, seconds precision."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


    def _clean_title(value: object) -> str:
        """Return a stripped, non-empty title, or raise ValidationError."""
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("title is required")
        return value.strip()


    def _clean_due_at(value: object) -> str | None:
        """Validate an optional ISO-8601 due date; return it unchanged (or None)."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValidationError("due_at must be an ISO-8601 datetime")
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValidationError("due_at must be an ISO-8601 datetime")
        return value


    def _row_to_dict(row) -> dict:
        """Convert a todos sqlite3.Row into a plain dict (done as bool)."""
        return {
            "id": row["id"],
            "title": row["title"],
            "due_at": row["due_at"],
            "done": bool(row["done"]),
            "notes": row["notes"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }


    def create_todo(data: dict) -> dict:
        """Insert a todo. Requires a non-empty title; due_at optional ISO-8601."""
        title = _clean_title(data.get("title"))
        due_at = _clean_due_at(data.get("due_at"))
        todo_id = execute(
            "INSERT INTO todos (title, due_at, notes) VALUES (?, ?, ?)",
            (title, due_at, data.get("notes")),
        )
        return get_todo(todo_id)


    def get_todo(todo_id: int) -> dict | None:
        """Return a single todo dict, or None if the id does not exist."""
        rows = query("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return _row_to_dict(rows[0]) if rows else None


    def list_todos(done: bool | None = None) -> list[dict]:
        """List todos in creation order, optionally filtered by done state."""
        if done is None:
            rows = query("SELECT * FROM todos ORDER BY id")
        else:
            rows = query(
                "SELECT * FROM todos WHERE done = ? ORDER BY id",
                (1 if done else 0,),
            )
        return [_row_to_dict(row) for row in rows]


    def update_todo(todo_id: int, data: dict) -> dict | None:
        """Patch a todo. Toggling ``done`` sets/clears ``completed_at``.

        Returns the updated dict, or None if the id does not exist.
        """
        current = get_todo(todo_id)
        if current is None:
            return None

        fields: dict = {}
        if "title" in data:
            fields["title"] = _clean_title(data.get("title"))
        if "due_at" in data:
            fields["due_at"] = _clean_due_at(data.get("due_at"))
        if "notes" in data:
            fields["notes"] = data.get("notes")
        if "done" in data:
            new_done = bool(data.get("done"))
            fields["done"] = 1 if new_done else 0
            if new_done and not current["done"]:
                fields["completed_at"] = _utc_now_iso()
            elif not new_done and current["done"]:
                fields["completed_at"] = None

        if fields:
            assignments = ", ".join(f"{col} = ?" for col in fields)
            params = tuple(fields.values()) + (todo_id,)
            execute(f"UPDATE todos SET {assignments} WHERE id = ?", params)

        return get_todo(todo_id)


    def delete_todo(todo_id: int) -> bool:
        """Delete a todo. Return True if a row was removed, else False."""
        if get_todo(todo_id) is None:
            return False
        execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        return True
    ```
  - Commit:
    ```bash
    git add pages/todos/models.py tests/test_todos_model.py
    git commit -m "feat(todos): add delete_todo"
    ```

---

**Definition of done for Task 06:**

- `pages/todos/__init__.py` and `pages/todos/models.py` exist; `models.py` exposes
  `create_todo`, `get_todo`, `list_todos`, `update_todo`, `delete_todo` with the exact
  contract signatures.
- `python -m pytest tests/test_todos_model.py -q` reports `18 passed`.
- Validation raises `core.errors.ValidationError` on empty/missing title and on a
  non-ISO-8601 `due_at`.
- Toggling `done` `0 -> 1` sets `completed_at` to a valid UTC ISO-8601 string; `1 -> 0`
  clears it to `None`.
- `list_todos(done=False)` excludes completed todos; `done` is returned as a Python `bool`.
- Only stdlib `sqlite3` (via `core.db`) is used — no ORM, no `schema.sql` edits.
