"""Grades: Campus sync, weak-spot ranking SQL, alert derivation, LLM readout.

Design principle throughout: a broken sync degrades to stale data, never to a
broken page. Every failure path is caught here and reported as a status string.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from core import campus
from core.db import execute, query, rollback
from pages.grades import gpa

log = logging.getLogger(__name__)

SYNC_KEY = "campus_synced_at"
ERROR_KEY = "campus_sync_error"
DISTRICT_KEY = "campus_district"
ANALYSIS_KEY = "campus_analysis"
OFFICIAL_GPA_KEY = "gpa_official"

THROTTLE = timedelta(hours=2)
DROP_WINDOW = timedelta(days=14)
DROP_POINTS = 2.0  # percentage points, not percent-of-percent
TS_FMT = "%Y-%m-%d %H:%M:%S"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stamp(dt: datetime | None = None) -> str:
    return (dt or _utcnow()).strftime(TS_FMT)


# --------------------------------------------------------------------------- #
# settings key/value
# --------------------------------------------------------------------------- #

def _get(key: str) -> str | None:
    row = query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
    return row["value"] if row else None


def _set(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
        (key, value),
    )


def _clear(key: str) -> None:
    execute("DELETE FROM settings WHERE key = %s", (key,))


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #

def _district(client_session=None) -> dict:
    """Resolved district base URL + app name, looked up once and cached.

    CAMPUS_BASE / CAMPUS_APP short-circuit the whole thing. Prefer them: the
    district-search service they replace answers 504 for long stretches.
    """
    creds = campus.credentials()
    if creds["base"] and creds["app_name"]:
        return {"base": creds["base"], "app_name": creds["app_name"]}

    cached = _get(DISTRICT_KEY)
    if cached:
        try:
            d = json.loads(cached)
            if d.get("base") and d.get("app_name"):
                return d
        except ValueError:
            pass  # corrupt cache: fall through and re-resolve
    d = campus.search_district(creds["district"], creds["state"], session=client_session)
    _set(DISTRICT_KEY, json.dumps(d))
    return d


def _upsert_course(c: dict, grade: dict) -> None:
    execute(
        "INSERT INTO courses (section_id, name, teacher, period, term, grade_pct, grade_letter, "
        "                     final_pct, in_gpa, credits, level, synced_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (section_id) DO UPDATE SET name=excluded.name, teacher=excluded.teacher, "
        "period=excluded.period, term=excluded.term, grade_pct=excluded.grade_pct, "
        "grade_letter=excluded.grade_letter, final_pct=excluded.final_pct, "
        "in_gpa=excluded.in_gpa, credits=excluded.credits, level=excluded.level, "
        "synced_at=excluded.synced_at",
        (c["section_id"], c["name"], c.get("teacher"), c.get("period"), c.get("term"),
         grade.get("grade_pct"), grade.get("grade_letter"), grade.get("final_pct"),
         grade.get("in_gpa", 0), grade.get("credits"), gpa.detect_level(c["name"]), _stamp()),
    )


def _record_history(section_id: str, pct) -> bool:
    """Insert a history row only when the percent actually moved. Returns True if inserted."""
    if pct is None:
        return False
    last = query(
        "SELECT grade_pct FROM grade_history WHERE section_id = %s "
        "ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (section_id,), one=True,
    )
    if last is not None and last["grade_pct"] is not None and abs(last["grade_pct"] - pct) < 0.01:
        return False
    execute(
        "INSERT INTO grade_history (section_id, grade_pct, recorded_at) VALUES (%s, %s, %s)",
        (section_id, pct, _stamp()),
    )
    return True


def _upsert_assignment(a: dict) -> None:
    execute(
        "INSERT INTO assignments (campus_id, section_id, name, category, points, total, due_at, missing, synced_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (campus_id) DO UPDATE SET section_id=excluded.section_id, name=excluded.name, "
        "category=excluded.category, points=excluded.points, total=excluded.total, "
        "due_at=excluded.due_at, missing=excluded.missing, synced_at=excluded.synced_at",
        (a["campus_id"], a["section_id"], a["name"], a.get("category"), a.get("points"),
         a.get("total"), a.get("due_at"), a.get("missing", 0), _stamp()),
    )


def _fresh() -> bool:
    ts = _get(SYNC_KEY)
    if not ts:
        return False
    try:
        return _utcnow() - datetime.strptime(ts[:19], TS_FMT) < THROTTLE
    except ValueError:
        return False


def sync(force: bool = False) -> dict:
    """Pull Campus into the local mirror. Never raises.

    Returns {"configured", "ran", "error", "synced_at", "courses", "assignments"}.
    """
    result = {"configured": True, "ran": False, "error": None,
              "synced_at": _get(SYNC_KEY), "courses": 0, "assignments": 0}

    if campus.credentials() is None:
        result["configured"] = False
        return result
    if not force and _fresh():
        return result

    try:
        creds = campus.credentials()
        d = _district()
        client = campus.Campus(d["base"], d["app_name"], creds["user"], creds["password"])
        client.login()
        courses = campus.parse_courses(client.roster())
        grades = campus.parse_grades(client.grades())

        for c in courses:
            grade = grades.get(c["section_id"], {})
            if grade.get("term"):
                c["term"] = grade["term"]  # the graded term beats the roster placement
            _upsert_course(c, grade)
            _record_history(c["section_id"], grade.get("grade_pct"))
            if not grade:
                continue  # no grade for this section means no grade detail to fetch
            for a in campus.parse_assignments(client.assignments(c["section_id"]), c["section_id"]):
                _upsert_assignment(a)
                result["assignments"] += 1
        result["courses"] = len(courses)

        result["synced_at"] = _stamp()
        _set(SYNC_KEY, result["synced_at"])
        _clear(ERROR_KEY)
        result["ran"] = True
    except Exception as e:  # network, auth, or a shape the parsers couldn't read
        rollback()  # Postgres refuses later statements on a poisoned transaction
        # Redacted before it is logged, stored, or rendered as the status line.
        msg = campus.redact(str(e) or e.__class__.__name__)
        log.warning("Campus sync failed: %s", msg)
        result["error"] = msg
        try:
            _set(ERROR_KEY, msg)
        except Exception:
            rollback()
    return result


def official_gpa() -> float | None:
    """The GPA off a report card, if the user has entered one. Accuracy baseline."""
    raw = _get(OFFICIAL_GPA_KEY)
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def set_official_gpa(value) -> float | None:
    if value in (None, ""):
        _clear(OFFICIAL_GPA_KEY)
        return None
    official = float(value)
    _set(OFFICIAL_GPA_KEY, str(official))
    return official


def status() -> dict:
    """What the page shows above the data: configured?, last sync, last error."""
    return {
        "configured": campus.credentials() is not None,
        "synced_at": _get(SYNC_KEY),
        "error": _get(ERROR_KEY),
    }


# --------------------------------------------------------------------------- #
# Weak-spot ranking (SQL only, no LLM)
# --------------------------------------------------------------------------- #

def weakest_courses() -> list[dict]:
    return [dict(r) for r in query(
        "SELECT c.section_id, c.name, c.teacher, c.grade_pct, c.grade_letter, "
        # GREATEST: extra credit scores above the total, and a course full of it
        # would otherwise report negative points lost.
        "       COALESCE(SUM(GREATEST(a.total - a.points, 0)), 0) AS points_lost "
        "FROM courses c "
        "LEFT JOIN assignments a ON a.section_id = c.section_id "
        "     AND a.points IS NOT NULL AND a.total IS NOT NULL "
        "GROUP BY c.section_id, c.name, c.teacher, c.grade_pct, c.grade_letter "
        "ORDER BY c.grade_pct ASC NULLS LAST, points_lost DESC"
    )]


def weakest_categories() -> list[dict]:
    """Across all courses: which kind of classwork costs the most."""
    return [dict(r) for r in query(
        "SELECT category, count(*) AS n, SUM(points) AS earned, SUM(total) AS possible, "
        "       SUM(points) / NULLIF(SUM(total), 0) * 100 AS pct "
        "FROM assignments "
        "WHERE category IS NOT NULL AND points IS NOT NULL AND total IS NOT NULL AND total > 0 "
        "GROUP BY category ORDER BY pct ASC NULLS LAST"
    )]


def categories_by_course() -> list[dict]:
    return [dict(r) for r in query(
        "SELECT c.name AS course, a.category, count(*) AS n, "
        "       SUM(a.points) / NULLIF(SUM(a.total), 0) * 100 AS pct "
        "FROM assignments a JOIN courses c ON c.section_id = a.section_id "
        "WHERE a.category IS NOT NULL AND a.points IS NOT NULL "
        "      AND a.total IS NOT NULL AND a.total > 0 "
        "GROUP BY c.name, a.category ORDER BY pct ASC NULLS LAST"
    )]


def ranking() -> dict:
    return {
        "courses": weakest_courses(),
        "categories": weakest_categories(),
        "by_course": categories_by_course(),
    }


# --------------------------------------------------------------------------- #
# Alerts — derived on read, nothing stored
# --------------------------------------------------------------------------- #

def missing_assignments(limit: int = 20) -> list[dict]:
    return [dict(r) for r in query(
        "SELECT a.name, a.due_at, a.total, c.name AS course "
        "FROM assignments a LEFT JOIN courses c ON c.section_id = a.section_id "
        "WHERE a.missing = 1 ORDER BY a.due_at DESC NULLS LAST LIMIT %s", (limit,)
    )]


def zero_scores(limit: int = 20) -> list[dict]:
    return [dict(r) for r in query(
        "SELECT a.name, a.due_at, a.total, c.name AS course "
        "FROM assignments a LEFT JOIN courses c ON c.section_id = a.section_id "
        "WHERE a.points = 0 AND a.total > 0 AND a.missing = 0 "
        "ORDER BY a.due_at DESC NULLS LAST LIMIT %s", (limit,)
    )]


def grade_drops() -> list[dict]:
    """Courses that fell DROP_POINTS or more within the last DROP_WINDOW."""
    since = _stamp(_utcnow() - DROP_WINDOW)
    return [dict(r) for r in query(
        "WITH win AS (SELECT section_id, grade_pct, recorded_at FROM grade_history "
        "             WHERE recorded_at >= %s AND grade_pct IS NOT NULL), "
        "     bounds AS (SELECT section_id, min(recorded_at) AS first_at, max(recorded_at) AS last_at "
        "                FROM win GROUP BY section_id) "
        "SELECT DISTINCT c.name AS course, b.section_id, f.grade_pct AS was, l.grade_pct AS now_pct, "
        "       (f.grade_pct - l.grade_pct) AS drop_pts "
        "FROM bounds b "
        "JOIN win f ON f.section_id = b.section_id AND f.recorded_at = b.first_at "
        "JOIN win l ON l.section_id = b.section_id AND l.recorded_at = b.last_at "
        "LEFT JOIN courses c ON c.section_id = b.section_id "
        "WHERE f.grade_pct - l.grade_pct >= %s "
        "ORDER BY drop_pts DESC", (since, DROP_POINTS)
    )]


def alerts() -> dict:
    return {
        "missing": missing_assignments(),
        "zeros": zero_scores(),
        "drops": grade_drops(),
    }


# --------------------------------------------------------------------------- #
# FRIDAY readout (LLM), cached by a hash of the ranking data
# --------------------------------------------------------------------------- #

PROMPT = (
    "You are F.R.I.D.A.Y., the user's study assistant. Below are their current course "
    "grades and their scoring rate by kind of classwork. In 3-5 sentences, say where "
    "they are weakest and why the numbers point there. Then give exactly one concrete "
    "action for this week, on its own final line starting with 'This week: '. "
    "No preamble, no lists, no flattery."
)


def ranking_hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def analysis(force: bool = False, client=None) -> dict:
    """Cached LLM readout. Re-runs only when the ranking data changes."""
    from core.llm import DeepSeekClient, LLMError

    data = ranking()
    if not data["courses"]:
        return {"configured": True, "cached": False, "text": None,
                "error": "No grades synced yet."}

    digest = ranking_hash(data)
    cached = _get(ANALYSIS_KEY)
    if cached and not force:
        try:
            blob = json.loads(cached)
            if blob.get("hash") == digest:
                return {"configured": True, "cached": True, "text": blob["text"], "error": None}
        except (ValueError, KeyError):
            pass

    client = client or DeepSeekClient()
    if not getattr(client, "api_key", ""):
        return {"configured": False, "cached": False, "text": None,
                "error": "FRIDAY analysis needs an LLM API key."}
    try:
        msg = client.complete([
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(data, default=str)},
        ])
        text = (msg.get("content") or "").strip()
    except LLMError as e:
        return {"configured": True, "cached": False, "text": None, "error": str(e)}

    if text:
        _set(ANALYSIS_KEY, json.dumps({"hash": digest, "text": text}))
    return {"configured": True, "cached": False, "text": text, "error": None}
