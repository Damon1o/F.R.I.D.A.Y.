# Infinite Campus grades — design

Date: 2026-07-29
Status: implemented and verified against the live portal (2026-07-29):
12 courses, 406 assignments synced.

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
  break the client. The paths below were verified live against Bellmore-Merrick
  (Campus 2025-26) during implementation.
- `mobile.infinitecampus.com/api/district/searchDistrict` — the service that maps a
  district name to its portal URL — answers 504 for long stretches. `CAMPUS_BASE`
  and `CAMPUS_APP` address the portal directly and skip it. Set them.
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

- `search_district(name, state)` — the flaky lookup above. Only called when
  `CAMPUS_BASE` / `CAMPUS_APP` are unset; the result is cached in `settings`.
- `login()` — `POST {base}verify.jsp` with `nonBrowser/username/password/appName`
  in the **body**, holding the session cookie on a `requests.Session`. The body,
  not the query string: a `requests` exception stringifies the URL, and that
  string is stored and rendered as the sync status.
  Answers `<AUTHENTICATION>success</AUTHENTICATION>` on either verdict's HTTP 200.
- `roster()` — `resources/portal/roster`. Flat list; `courseName` and
  `teacherDisplay` sit on the item, but period and term are under
  `sectionPlacements[]`.
- `grades()` — `resources/portal/grades`. Nests
  `enrollment -> terms[] -> courses[] -> gradingTasks[]`. One enrollment per
  school year; the future year arrives with `terms: null`. There is **no**
  `progressPercent` on a task: the percent is
  `progressPointsEarned / progressTotalPoints`, and `score` is the posted mark
  (a 2822/2900 course posts `score: "96"`), so points are the truth and `score`
  is only a fallback. Later terms overwrite earlier ones, leaving the most
  recent graded term.
- `assignments(section_id)` — `resources/portal/grades/detail/{sectionID}`. This
  is the only path that carries assignment rows; every `assignment/section/...`
  path 404s. Shape: `details[] -> categories[] -> assignments[]`, where the
  category name ("Homework", "Labs", "Quizzes", "Tests and Papers") exists only
  on the enclosing category node — which is why the parser walks the tree by hand.
  Rows carry `objectSectionID`, `scorePoints`, `totalPoints`, `dueDate`,
  `missing`, and `dropped` (dropped rows are skipped).

Credentials, from env: `CAMPUS_USER`, `CAMPUS_PASS`, plus either
`CAMPUS_BASE` + `CAMPUS_APP` (preferred) or `CAMPUS_DISTRICT` + `CAMPUS_STATE`.
`campus.redact()` scrubs credential values from any message before it is logged,
stored, or displayed.
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
- Weakest courses: current percent ascending, with total points lost. Points lost
  clamps at zero per assignment — extra credit scores above the total, and a course
  full of it would otherwise report negative loss.
- Weakest categories: `SUM(points) / SUM(total)` grouped by `category`, both across
  all courses and per course. This answers "which kind of classwork costs me most".

**FRIDAY readout (LLM).** `POST /api/grades/analysis` sends the ranking tables — not
raw assignment rows, keeping the prompt small — to `core.llm` and returns 3-5
sentences plus one action for the week. Cached in `settings` under a key derived from
a hash of the ranking data, so it re-runs only when grades actually change.
Button-triggered. No API key means the button reports "not configured".

### GPA

The portal publishes no GPA: every `transcript`, `gpa` and `reportCard` path 404s.
So `pages/grades/gpa.py` derives one. That is the feature — when the school hides
the number, the number is still here.

The rule is the district's own, quoted from the Bellmore-Merrick *Catalog of
Courses 2026-2027*, "Student Transcripts" (identical wording in the 25-26
edition):

> Weighted Grades: "Weighted" grades appear on the transcripts of all students.
> Each course grade is "weighted" as follows:
> Advanced Placement Courses — 5 points added.
> Honors, Accelerated, and Advanced Courses — 2 points added.

Source: `files.smartsites.parentsquare.com/6369/course_catalog_2026-2027.pdf`
(the site serves it through a JS viewer; the PDF is directly addressable).

Three consequences:

- The bonus lands on the **course grade**, so these are numeric 0-100 averages,
  not 4.0-scale points.
- The +2 tier is three categories, not one: Honors, Accelerated, **and Advanced**.
  Detection has to match all three while keeping "Advanced Placement" at +5.
- That last point is genuinely ambiguous in practice — the district also offers
  courses merely *named* "Advanced Photography" and "Advanced Sculpture". Either
  guess moves the GPA, so every synced course carries a level selector and pinned
  levels live in `gpa_levels`, keyed by course name so they survive a resync.

A course counts only when Campus's own `includedInTermGPA` is set, which is how
Phys. Ed., lunch and lab sections drop out on their own.

**The combining formula**, which the catalog does not publish, is pinned exactly
by an official Mepham transcript:

```
unweighted = SUM(mark * weight) / SUM(weight)
weighted   = SUM((mark + bonus) * weight) / SUM(weight)
```

Verified against the transcript generated 2026-07-29 over grades 8 and 9:
`SUM(weight)` 9.5, `SUM(mark * weight)` 928 → **97.6842**, plus 14 points of bonus
→ **99.1579**. Both reproduce the printed figures to four decimals, and
`test_reproduces_the_official_transcript_exactly` locks that in.

Two things the transcript settled that guessing had gotten wrong:

- **Weight is not credit.** Phys. Ed. prints 0.500 credit against Weight 0.0000 —
  it earns credit and no GPA. Campus publishes neither number.
- **The marking-period inference is only an estimate.** It calls STEAM Comp Sci a
  half-credit semester course; the transcript prints 0.25. So weight is inferred
  by default and pinnable per course in `gpa_levels`, alongside level.

There is exactly one model now, not a menu of four. The transcript's own figures
are stored and shown as a delta beside the computed pair, so a regression is
visible immediately rather than silently plausible.

The catalog publishes no exclusion list, no class-rank formula, and no GPA
starting grade. It does publish credits as "(Year Course, 1 Unit)" /
"(Semester Course, .5 Unit)".

The GPA card renders **outside** the Campus-configured gate: it is computed from
stored final grades and hand-entered years, so it survives an unreachable portal —
which is the point of the feature.

Inputs come from each course's posted **Final Grade** task. Two rules make this
correct, both learned from live data:

- Task selection is by name, never by position. One term serves MP, Regents and
  Final Grade together; taking the last one made a course grade the Regents score.
  Standalone exams (Regents, Final Exam, Mid-Term) are never the course grade.
- A posted final uses the **mark**, not the gradebook ratio. A course posting
  `score: "98"` on a 2822/2900 gradebook is a 98 — that is what the report card
  says. Marking-period grades keep using the points ratio, which is the live
  average and ranks weak spots more finely.

Credits are not published, so they are inferred: a course graded in 2 of 4 marking
periods is a half-credit semester course. Because that inference could be wrong,
four numbers are reported — weighted and unweighted, each equal-credit and
credit-scaled — and the user enters the GPA from a report card. `gpa.compare()`
ranks the four by distance from it; the closest is the district's model and a
delta of zero means the local calculation is exact. Verified against the live
year: unweighted 98.50, weighted 99.75, both under the equal-credit model.

The GPA starts in 8th grade, which Campus will not serve (only the current and
next enrollment come back). Those years are hand-entered into `gpa_courses` and
never touched by sync.

**Alerts strip.** Top of the page, derived on read, nothing stored:
- assignments with `missing = 1`
- scored zeros
- any `grade_history` drop of 2 percentage points or more within the last 14 days

### Routes

| Route | Method | Purpose |
|---|---|---|
| `/grades` | GET | Page. Throttled sync, then render GPA + ranking + alerts |
| `/api/grades/sync` | POST | Forced resync, returns fresh summary JSON |
| `/api/grades/analysis` | POST | LLM readout, cached by ranking hash |
| `/api/gpa` | GET | Recomputed GPA, the four models, the official number |
| `/api/gpa/courses` | POST | Add a hand-entered year's course |
| `/api/gpa/courses/<id>` | DELETE | Remove one |
| `/api/gpa/level` | POST | Pin a course's level, or `auto` to clear the pin |
| `/api/gpa/official` | POST | Store the report-card GPA for the accuracy check |

The page shows the GPA panel and Weakest courses. The category breakdowns
("weakest kinds of classwork", "by course and category") are computed and fed to
the LLM readout, but are no longer rendered — the page earns its width back.

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
