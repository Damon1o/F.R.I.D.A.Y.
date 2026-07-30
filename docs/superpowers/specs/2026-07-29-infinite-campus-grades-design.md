# Infinite Campus grades — design

Date: 2026-07-29
Status: implemented (2026-07-29). Portal endpoint paths still need verification
against the live district — see Constraints.

## Purpose

Pull the student's own Infinite Campus grades and assignments into F.R.I.D.A.Y., then
surface where performance is weakest — both by course and by kind of classwork
(homework vs test vs project) — so study effort goes where it pays.

Single user. Read-only against Infinite Campus; nothing is ever written back.

## Constraints

Infinite Campus publishes no student-facing API. The only route for an individual
student is the Campus Student portal's own JSON endpoints, authenticated with the
student's district credentials. Consequences accepted up front:

- Credentials are stored as environment variables.
- The endpoints are versioned by district and undocumented. A district upgrade can
  break the client. Exact paths are verified against the live district during
  implementation, not assumed from this document.
- The app runs on Vercel serverless. Some districts block datacenter IP ranges. If
  the live pull 403s from Vercel, the fallback is a local sync script on the user's
  PC that POSTs to the app's API — a change of transport only, not of schema or UI.

## Decisions

| Question | Decision |
|---|---|
| Data source | Stored credentials, server-side pull |
| Sync trigger | On page load, throttled to once per 2h, plus a manual Refresh |
| Analysis | SQL weak-spot ranking + LLM written readout + trend/drop alerts |
| Alert destination | Grades page only. No writes into Tasks, no dashboard widget |
| Campus client | Hand-rolled ~50-line client on `requests`. No new dependency |

Rejected: the `infinite-campus` PyPI package (a sparse wrapper around the same four
calls — a dependency bought for 50 lines); Playwright headless login (~400MB in a
Vercel function, ~10s per sync).

## Architecture

Follows the existing page-module pattern: `core/` holds I/O-free-ish integration
code, `pages/<name>/` holds `models.py` (SQL) and `routes.py` (HTTP).

```
core/campus.py          Campus portal client. No Flask imports.
pages/grades/models.py  Sync, upsert, ranking SQL, alert derivation
pages/grades/routes.py  /grades page, /api/grades/sync, /api/grades/analysis
templates/grades.html   Page
schema.sql              courses, assignments, grade_history
```

### core/campus.py

No Flask imports, so it is unit-testable against recorded JSON fixtures with no
network.

- `district(name, state)` — `GET mobile.infinitecampus.com/api/district/searchDistrict`,
  returns district base URL and app name. Resolved once, cached in `settings`.
- `login()` — `POST {base}/campus/verify.jsp?nonBrowser=true&username=&password=&appName=`,
  holds the session cookie on a `requests.Session`.
- `roster()`, `grades()`, `assignments(section_id)` — portal JSON endpoints.

Credentials, from env: `CAMPUS_DISTRICT`, `CAMPUS_STATE`, `CAMPUS_USER`, `CAMPUS_PASS`.
Absent credentials is not an error — the page renders empty with a "not configured"
line, matching how the weather and email tools already degrade.

### Schema

Appended to `schema.sql` in the existing style (`TEXT` timestamps, `IF NOT EXISTS`).

```sql
CREATE TABLE IF NOT EXISTS courses (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id TEXT UNIQUE NOT NULL,   -- Campus sectionID: the sync key
    name       TEXT NOT NULL,
    teacher    TEXT,
    period     TEXT,
    term       TEXT,
    grade_pct  REAL,
    grade_letter TEXT,
    synced_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignments (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campus_id  TEXT UNIQUE NOT NULL,
    section_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    category   TEXT,                   -- Homework / Test / Project — powers category ranking
    points     REAL,
    total      REAL,
    due_at     TEXT,
    missing    INTEGER NOT NULL DEFAULT 0,
    synced_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grade_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    section_id  TEXT NOT NULL,
    grade_pct   REAL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS assignments_section_idx ON assignments (section_id);
CREATE INDEX IF NOT EXISTS grade_history_section_idx ON grade_history (section_id, recorded_at DESC);
```

Writes upsert on `section_id` / `campus_id`, so re-syncing is idempotent. A
`grade_history` row is inserted only when a course's percent differs from its last
recorded value — that is what makes drop detection work without a cron.

### Sync

`models.sync(force=False)`:

1. Return early if `settings['campus_synced_at']` is under 2 hours old and not forced.
2. Log in, fetch roster and grades, fetch assignments per section.
3. Upsert courses and assignments; insert `grade_history` rows on change.
4. Stamp `settings['campus_synced_at']`.

Called from the `/grades` route and from `POST /api/grades/sync` (force=True, the
Refresh button). Failure is caught and recorded, never raised to the page: the page
renders cached data with a "last synced N ago" or "sync failed" line.

### Analysis

Three layers, cheapest first.

**Weak-spot ranking (SQL, no LLM).** Two tables on the page:
- Weakest courses: current percent ascending, with total points lost.
- Weakest categories: `SUM(points) / SUM(total)` grouped by `category`, both across
  all courses and per course. This answers "which kind of classwork costs me most".

**FRIDAY readout (LLM).** `POST /api/grades/analysis` sends the ranking tables — not
raw assignment rows, keeping the prompt small — to `core.llm` and returns 3-5
sentences plus one action for the week. Cached in `settings` under a key derived from
a hash of the ranking data, so it re-runs only when grades actually change.
Button-triggered. No API key means the button reports "not configured".

**Alerts strip.** Top of the page, derived on read, nothing stored:
- assignments with `missing = 1`
- scored zeros
- any `grade_history` drop of 2 percentage points or more within the last 14 days

### Routes

| Route | Method | Purpose |
|---|---|---|
| `/grades` | GET | Page. Throttled sync, then render ranking + alerts |
| `/api/grades/sync` | POST | Forced resync, returns fresh summary JSON |
| `/api/grades/analysis` | POST | LLM readout, cached by ranking hash |

### Navigation

New `EDUCATIONAL` group in `templates/base.html`, between the main nav and the
Settings footer:

```
EDUCATIONAL
  graduation-cap    Grades      -> grades.grades_page
  book-open-check   SAT Prep    -> sat.sat_page
```

Both Lucide SVGs must be vendored into `static/vendor/lucide/` (hand-vendored set,
51 files at time of writing). No emoji, no CDN.

**SAT Prep ships as a stub page this round.** It is a separate subsystem — content
generation and score-report ingest, sharing only a nav group with this feature — and
gets its own spec next.

## Error handling

| Failure | Behavior |
|---|---|
| Credentials absent | Page renders "not configured". No exception |
| Login rejected | Cached data + "sync failed: sign-in rejected" |
| Endpoint 404 / shape changed | Cached data + "sync failed". Parse errors are logged with the offending key |
| District blocks Vercel IP | Cached data + "sync failed". Documented fallback: local sync script POSTing to `/api/grades/sync` |
| No LLM key | Analysis button reports not configured. Ranking and alerts still work |

The design principle throughout: a broken sync degrades to stale data, never to a
broken page.

## Testing

`tests/test_grades.py`, no network:

1. Client parsing against recorded JSON fixtures for roster, grades, assignments.
2. Upsert idempotency — syncing the same fixture twice yields one row per assignment
   and no duplicate `grade_history` rows.
3. `grade_history` gains a row only when the percent changes.
4. Ranking SQL — weakest course and weakest category on a known fixture.
5. Alert derivation — missing, zero, and a seeded 4-point drop.
6. Analysis endpoint against a stub LLM client, and the cache-by-hash behavior.
7. Nav markup contains both Educational links.

## Out of scope

- Writing anything back to Infinite Campus.
- Multiple students or guardian accounts.
- Dashboard widget for grades.
- Auto-creating tasks from missing assignments.
- The SAT Prep feature itself, beyond a stub page and nav entry.
