### Task 04: Events model (CRUD + validation)

> **For agentic workers:** Execute steps top-to-bottom in order. Steps use checkbox (`- [ ]`) syntax for tracking. Strict TDD: write the failing test, watch it fail, implement the minimal code, watch it pass, commit.

**Context (this task is self-contained — read this before starting):**

Kiko is a single-user, localhost Flask productivity app. This task implements the **events data-access layer** for the calendar page: five functions that create/read/update/delete/list event rows in SQLite, with input validation. No routes, no templates, no HTTP here — those are Task 05.

The functions are backed by `core.db` (Task 02), a thin stdlib-`sqlite3` helper. `core.db.execute()` runs a write, commits, and returns `lastrowid`; `core.db.query()` runs a read and returns a `list[sqlite3.Row]`. Both require a Flask **application context** (they read the DB path from `current_app.config["DATABASE"]` and cache the connection on `flask.g`), which is why the test creates an app via `app.create_app` (Task 01) and pushes an app context.

The `events` table is created by `core.db.init_db()` (which runs `schema.sql`, from Task 02). Its columns are exactly:

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
```

**Relevant global constraints (honor all):**
- Python 3, Flask app-factory pattern. Persistence is stdlib `sqlite3` **only** — no SQLAlchemy / no ORM. Use `core.db.query` / `core.db.execute`.
- Datetimes are stored as ISO-8601 UTC **text**. Validate parseability with `datetime.fromisoformat`.
- Returned dicts expose `all_day` as a Python `bool` (the DB stores it as `0`/`1`).
- Validation failures raise `core.errors.ValidationError` (Task 01); routes (Task 05) map that to HTTP 400.
- DRY / YAGNI: no priority, tags, recurrence, or reminders in Phase 1.

**No files are recovered from git history for this task.** The prior `pages/calendar/models.py` at commit `bb6176f` used SQLAlchemy (`db.Model`, `db.Column`, an `Event` ORM class) and a different, richer schema (`start_datetime`/`end_datetime`/`recurrence_rule`). It is incompatible with the stdlib-`sqlite3` contract and the Phase 1 schema, so this task writes `pages/calendar/models.py` fresh. Do **not** `git show`-restore it.

**Files:**
- Create: `pages/calendar/__init__.py` (empty package marker)
- Create: `pages/calendar/models.py`
- Modify: none
- Test: `tests/test_events_model.py`

**Interfaces:**

- Consumes:
  - `core.db.query(sql: str, params: tuple = ()) -> list[sqlite3.Row]` (Task 02)
  - `core.db.execute(sql: str, params: tuple = ()) -> int` — returns `lastrowid`, commits (Task 02)
  - `core.db.init_db() -> None` — runs `schema.sql`, creating the `events` table (Task 02, used by the test fixture)
  - `core.errors.ValidationError(Exception)` — raised on bad input (Task 01)
  - `app.create_app(test_config: dict | None = None) -> Flask` — used **only by the test fixture** to obtain an app context with `DATABASE=':memory:'` (Task 01)
- Produces (later tasks — Task 05 routes, Task 08 dashboard — rely on these EXACT signatures):
  - `create_event(data: dict) -> dict` — keys: `title`(req), `start_at`(req), `end_at`?, `all_day`?, `location`?, `notes`?
  - `get_event(event_id: int) -> dict | None`
  - `list_events(from_: str | None = None, to: str | None = None) -> list[dict]`
  - `update_event(event_id: int, data: dict) -> dict | None`
  - `delete_event(event_id: int) -> bool`
  - Every returned dict includes `id` and `created_at`, and exposes `all_day` as a `bool`.

---

- [ ] **Step 1: Create the calendar package marker**

Create an empty `pages/calendar/__init__.py` so `pages.calendar.models` is importable. (`pages/` resolves as a namespace package; only the `calendar` sub-package needs a marker per this task's file scope.)

Run (from the repo root):

```bash
mkdir -p pages/calendar
touch pages/calendar/__init__.py
```

Contents of `pages/calendar/__init__.py`: empty file (zero bytes). Do not add anything.

- [ ] **Step 2: Write the failing test**

Create `tests/test_events_model.py` with this exact content:

```python
import pytest

from app import create_app
from core.db import init_db
from core.errors import ValidationError
from pages.calendar.models import (
    create_event,
    delete_event,
    get_event,
    list_events,
    update_event,
)


@pytest.fixture
def ctx():
    """Push an app context backed by a fresh in-memory SQLite DB with the schema applied."""
    app = create_app({"DATABASE": ":memory:", "SECRET_KEY": "test"})
    with app.app_context():
        init_db()
        yield


def test_create_and_get_event_round_trip(ctx):
    created = create_event(
        {
            "title": "Standup",
            "start_at": "2026-07-22T09:00:00",
            "end_at": "2026-07-22T09:15:00",
            "location": "Zoom",
            "notes": "daily sync",
        }
    )
    assert created["id"] > 0
    assert created["title"] == "Standup"
    assert created["start_at"] == "2026-07-22T09:00:00"
    assert created["end_at"] == "2026-07-22T09:15:00"
    assert created["location"] == "Zoom"
    assert created["notes"] == "daily sync"
    assert created["all_day"] is False
    assert "created_at" in created

    fetched = get_event(created["id"])
    assert fetched == created


def test_get_event_missing_returns_none(ctx):
    assert get_event(4242) is None


def test_create_event_defaults_all_day_false(ctx):
    created = create_event({"title": "No end", "start_at": "2026-07-22T09:00:00"})
    assert created["end_at"] is None
    assert created["all_day"] is False


def test_create_event_coerces_all_day_to_bool(ctx):
    created = create_event(
        {"title": "Holiday", "start_at": "2026-07-22T00:00:00", "all_day": 1}
    )
    assert created["all_day"] is True


def test_create_event_empty_title_raises(ctx):
    with pytest.raises(ValidationError):
        create_event({"title": "   ", "start_at": "2026-07-22T09:00:00"})


def test_create_event_missing_start_at_raises(ctx):
    with pytest.raises(ValidationError):
        create_event({"title": "No start"})


def test_create_event_bad_start_at_raises(ctx):
    with pytest.raises(ValidationError):
        create_event({"title": "Bad date", "start_at": "not-a-date"})


def test_create_event_end_before_start_raises(ctx):
    with pytest.raises(ValidationError):
        create_event(
            {
                "title": "Backwards",
                "start_at": "2026-07-22T10:00:00",
                "end_at": "2026-07-22T09:00:00",
            }
        )


def test_list_events_no_filter_returns_all_sorted(ctx):
    create_event({"title": "Late", "start_at": "2026-07-25T09:00:00"})
    create_event({"title": "Early", "start_at": "2026-07-20T09:00:00"})
    titles = [e["title"] for e in list_events()]
    assert titles == ["Early", "Late"]


def test_list_events_range_filter_includes_and_excludes(ctx):
    create_event({"title": "Before", "start_at": "2026-07-20T09:00:00"})
    create_event({"title": "Inside", "start_at": "2026-07-22T09:00:00"})
    create_event({"title": "After", "start_at": "2026-07-25T09:00:00"})

    result = list_events(from_="2026-07-21T00:00:00", to="2026-07-23T00:00:00")
    assert [e["title"] for e in result] == ["Inside"]


def test_update_event_changes_fields(ctx):
    created = create_event({"title": "Old", "start_at": "2026-07-22T09:00:00"})
    updated = update_event(created["id"], {"title": "New", "all_day": True})
    assert updated["title"] == "New"
    assert updated["all_day"] is True
    assert updated["start_at"] == "2026-07-22T09:00:00"  # untouched field preserved


def test_update_event_missing_id_returns_none(ctx):
    assert update_event(9999, {"title": "Nope"}) is None


def test_update_event_end_before_start_raises(ctx):
    created = create_event({"title": "X", "start_at": "2026-07-22T10:00:00"})
    with pytest.raises(ValidationError):
        update_event(created["id"], {"end_at": "2026-07-22T09:00:00"})


def test_delete_event_returns_true_then_false(ctx):
    created = create_event({"title": "Temp", "start_at": "2026-07-22T09:00:00"})
    assert delete_event(created["id"]) is True
    assert get_event(created["id"]) is None
    assert delete_event(created["id"]) is False
```

- [ ] **Step 3: Run the test and watch it fail**

Run (from the repo root):

```bash
python -m pytest tests/test_events_model.py -v
```

Expected: a **collection error**, because `pages/calendar/models.py` does not exist yet:

```
ModuleNotFoundError: No module named 'pages.calendar.models'
```

(No tests run — pytest fails at import time. That is the expected "red".)

- [ ] **Step 4: Write the minimal implementation**

Create `pages/calendar/models.py` with this exact content:

```python
"""Event CRUD + validation for the calendar page.

Backed by stdlib sqlite3 via core.db. All datetimes are ISO-8601 UTC text;
`all_day` is stored as 0/1 and returned as a Python bool.
"""
from datetime import datetime

from core.db import execute, query
from core.errors import ValidationError


def _parse_iso(value, field):
    """Return a datetime parsed from an ISO-8601 string, or raise ValidationError."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a valid ISO-8601 datetime")


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict with all_day coerced to bool."""
    data = dict(row)
    data["all_day"] = bool(data["all_day"])
    return data


def create_event(data):
    title = (data.get("title") or "").strip()
    if not title:
        raise ValidationError("title is required")

    start_at = data.get("start_at")
    if not start_at:
        raise ValidationError("start_at is required")
    start_dt = _parse_iso(start_at, "start_at")

    end_at = data.get("end_at")
    if end_at:
        if _parse_iso(end_at, "end_at") < start_dt:
            raise ValidationError("end_at must be on or after start_at")
    else:
        end_at = None

    all_day = 1 if data.get("all_day") else 0

    event_id = execute(
        "INSERT INTO events (title, start_at, end_at, all_day, location, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, start_at, end_at, all_day, data.get("location"), data.get("notes")),
    )
    return get_event(event_id)


def get_event(event_id):
    rows = query("SELECT * FROM events WHERE id = ?", (event_id,))
    return _row_to_dict(rows[0]) if rows else None


def list_events(from_=None, to=None):
    sql = "SELECT * FROM events"
    clauses = []
    params = []
    if from_ is not None:
        clauses.append("start_at >= ?")
        params.append(from_)
    if to is not None:
        clauses.append("start_at <= ?")
        params.append(to)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY start_at"
    return [_row_to_dict(r) for r in query(sql, tuple(params))]


def update_event(event_id, data):
    existing = get_event(event_id)
    if existing is None:
        return None

    fields = {}

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("title is required")
        fields["title"] = title

    if "start_at" in data:
        start_at = data.get("start_at")
        if not start_at:
            raise ValidationError("start_at is required")
        _parse_iso(start_at, "start_at")
        fields["start_at"] = start_at

    if "end_at" in data:
        end_at = data.get("end_at")
        if end_at:
            _parse_iso(end_at, "end_at")
            fields["end_at"] = end_at
        else:
            fields["end_at"] = None

    if "all_day" in data:
        fields["all_day"] = 1 if data.get("all_day") else 0

    if "location" in data:
        fields["location"] = data.get("location")

    if "notes" in data:
        fields["notes"] = data.get("notes")

    # Enforce end_at >= start_at using the effective (post-update) values.
    effective_start = fields.get("start_at", existing["start_at"])
    effective_end = fields.get("end_at", existing["end_at"])
    if effective_end:
        if _parse_iso(effective_end, "end_at") < _parse_iso(effective_start, "start_at"):
            raise ValidationError("end_at must be on or after start_at")

    if fields:
        assignments = ", ".join(f"{col} = ?" for col in fields)
        params = tuple(fields.values()) + (event_id,)
        execute(f"UPDATE events SET {assignments} WHERE id = ?", params)

    return get_event(event_id)


def delete_event(event_id):
    if get_event(event_id) is None:
        return False
    execute("DELETE FROM events WHERE id = ?", (event_id,))
    return True
```

Notes for the implementer (do not change behavior, just understand it):
- The `f"{col} = ?"` interpolation in `update_event` is injection-safe: `col` values come only from the fixed set of dict keys this function itself sets (`title`, `start_at`, `end_at`, `all_day`, `location`, `notes`) — never from user input. Values always go through `?` placeholders.
- `end_at` truthiness (`if end_at:`) treats both `None` and `""` as "no end", normalizing to `NULL`.
- `update_event` re-validates ordering against the row's existing `start_at`/`end_at` so a partial PATCH (e.g. `end_at` only) can't create a backwards interval.

- [ ] **Step 5: Run the test and watch it pass**

Run (from the repo root):

```bash
python -m pytest tests/test_events_model.py -v
```

Expected: **14 passed** — every test in `tests/test_events_model.py` green, e.g.:

```
tests/test_events_model.py::test_create_and_get_event_round_trip PASSED
tests/test_events_model.py::test_get_event_missing_returns_none PASSED
tests/test_events_model.py::test_create_event_defaults_all_day_false PASSED
tests/test_events_model.py::test_create_event_coerces_all_day_to_bool PASSED
tests/test_events_model.py::test_create_event_empty_title_raises PASSED
tests/test_events_model.py::test_create_event_missing_start_at_raises PASSED
tests/test_events_model.py::test_create_event_bad_start_at_raises PASSED
tests/test_events_model.py::test_create_event_end_before_start_raises PASSED
tests/test_events_model.py::test_list_events_no_filter_returns_all_sorted PASSED
tests/test_events_model.py::test_list_events_range_filter_includes_and_excludes PASSED
tests/test_events_model.py::test_update_event_changes_fields PASSED
tests/test_events_model.py::test_update_event_missing_id_returns_none PASSED
tests/test_events_model.py::test_update_event_end_before_start_raises PASSED
tests/test_events_model.py::test_delete_event_returns_true_then_false PASSED

============================== 14 passed in 0.xxs ==============================
```

- [ ] **Step 6: Commit**

Run (from the repo root):

```bash
git add pages/calendar/__init__.py pages/calendar/models.py tests/test_events_model.py
git commit -m "feat(calendar): add events model with CRUD and validation"
```
