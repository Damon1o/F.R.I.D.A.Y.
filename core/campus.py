"""Infinite Campus Student portal client.

Infinite Campus publishes no student API. This talks to the portal's own JSON
endpoints with the student's district credentials — read-only, nothing is ever
written back.

No Flask imports: the parsers are pure functions over decoded JSON, so they are
unit-testable against recorded fixtures with no network.

Endpoints, verified live against a Campus 2025-26 portal:

    POST verify.jsp                            -> <AUTHENTICATION>success</...>
    GET  resources/portal/roster               -> [{sectionID, courseName, ...}]
    GET  resources/portal/grades               -> [{enrollmentID, terms:[{courses:[
                                                    {gradingTasks:[...]}]}]}]
    GET  resources/portal/grades/detail/{sid}  -> {terms:[], details:[{task,
                                                    categories:[{name, assignments:[]}]}]}

`mobile.infinitecampus.com/api/district/searchDistrict` is only a convenience for
finding the base URL, and it is unreliable (it answers 504 for long stretches).
Set CAMPUS_BASE and CAMPUS_APP and it is never called.
"""
import os

import requests

DISTRICT_SEARCH = "https://mobile.infinitecampus.com/api/district/searchDistrict"
TIMEOUT = 30
# Campus answers some paths with the sign-in page unless the request looks like a
# browser. Cheaper than debugging an empty roster later.
USER_AGENT = "Mozilla/5.0"


class CampusError(RuntimeError):
    """Any failure reaching, authenticating to, or decoding Infinite Campus."""


def _first(d: dict, *keys, default=None):
    """First present, non-empty value among `keys`. Order matters."""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


# --------------------------------------------------------------------------- #
# Parsers (pure). Field names come from a live portal; aliases cover the older
# spellings other districts still serve.
# --------------------------------------------------------------------------- #

def parse_courses(roster_json) -> list[dict]:
    """Roster -> one row per section. Period and term live in sectionPlacements."""
    out: dict[str, dict] = {}
    for item in _as_list(roster_json):
        if not isinstance(item, dict):
            continue
        sid = _first(item, "sectionID", "sectionId")
        name = _first(item, "courseName", "name")
        if sid is None or not name:
            continue
        sid = str(sid)
        placement = next((p for p in _as_list(item.get("sectionPlacements"))
                          if isinstance(p, dict)), {})
        out[sid] = {
            "section_id": sid,
            "name": str(name),
            "teacher": _first(item, "teacherDisplay", "teacherName")
                       or _first(placement, "teacherDisplay"),
            "period": _first(placement, "periodName", "periodSequence"),
            "term": _first(placement, "termName") or _first(item, "termName"),
        }
    return list(out.values())


def _task_percent(task: dict):
    """Percent for one grading task.

    Points are the truth: districts on numeric grading scales report `score` as a
    0-100 mark that is NOT the percent (a 2822/2900 course posts score "96"), and
    districts on letter scales report a letter there. Fall back only if points are
    missing.
    """
    earned = _num(task.get("progressPointsEarned"))
    total = _num(task.get("progressTotalPoints"))
    if earned is not None and total:
        return earned / total * 100
    pct = _num(_first(task, "progressPercent", "percent"))
    if pct is not None:
        return pct
    return _num(_first(task, "progressScore", "score"))


def _posted_pct(task: dict):
    """Percent for a *posted* task, where the mark the teacher entered is the truth.

    The inverse preference of `_task_percent`: a Final Grade of "98" on a course
    whose gradebook reads 2822/2900 (97.3) is 98, because 98 is what the teacher
    posted and what lands on the report card. Points only fill in when the posted
    mark isn't numeric.
    """
    score = _num(_first(task, "score", "progressScore"))
    return score if score is not None else _task_percent(task)


def _task_letter(task: dict):
    """The posted mark, but only when it isn't just the percent again."""
    raw = _first(task, "score", "progressScore")
    if raw is None or _num(raw) is not None:
        return None
    return str(raw)


# A course carries several grading tasks. Only two kinds describe the course
# itself; the rest are standalone assessments that must never be mistaken for it.
FINAL_TASK = "final grade"
EXAM_TASKS = ("regents", "final exam", "mid-term exam", "midterm exam", "midterm",
              "mid-term", "exam")


def _task_kind(task: dict) -> str:
    """'final' (the posted course grade), 'exam' (a standalone test), or 'term'."""
    name = str(_first(task, "taskName", "name", default="")).strip().lower()
    if name == FINAL_TASK or name.startswith("final grade"):
        return "final"
    if name in EXAM_TASKS:
        return "exam"
    return "term"


def parse_grades(grades_json) -> dict[str, dict]:
    """Grades -> {section_id: {grade_pct, grade_letter, term, final_pct, in_gpa, credits}}.

    Task selection is explicit, not positional. A Biology course posts MP=100,
    Regents=89 and Final Grade=98 in one term; taking whichever arrived last would
    make the course grade the Regents score. Preference is the posted Final Grade,
    then the most recent marking-period grade. Standalone exams are ignored.

    `in_gpa` mirrors Campus's own `includedInTermGPA`, which is how Phys. Ed. and
    lunch drop out. `credits` is the share of the year the course ran: a course
    graded in 2 of 4 marking periods is a half-credit semester course.
    """
    acc: dict[str, dict] = {}
    for enrollment in _as_list(grades_json):
        if not isinstance(enrollment, dict) or not enrollment.get("terms"):
            continue  # future-year enrollments arrive with terms: null
        terms = sorted(_as_list(enrollment["terms"]),
                       key=lambda t: _num(t.get("termSeq")) or 0)
        for term in terms:
            for course in _as_list(term.get("courses")):
                if not isinstance(course, dict) or course.get("dropped"):
                    continue
                sid = _first(course, "sectionID", "sectionId")
                if sid is None:
                    continue
                e = acc.setdefault(str(sid), {"final": None, "term": None,
                                              "in_gpa": False, "term_ids": set(),
                                              "total_terms": len(terms)})
                e["total_terms"] = max(e["total_terms"], len(terms))
                for task in _as_list(course.get("gradingTasks")):
                    if not isinstance(task, dict):
                        continue
                    if task.get("includedInTermGPA"):
                        e["in_gpa"] = True
                    kind = _task_kind(task)
                    if kind == "exam":
                        continue
                    if kind == "term":
                        e["term_ids"].add(_first(term, "termID", "termName"))
                    # A posted final is the report-card number; a marking-period
                    # grade is a live gradebook average, so points read truer there.
                    pct = _posted_pct(task) if kind == "final" else _task_percent(task)
                    if pct is None:
                        continue
                    # Terms are visited in sequence, so the last write wins and the
                    # most recent graded term survives.
                    e[kind] = {"pct": pct, "letter": _task_letter(task),
                               "term": _first(term, "termName") or _first(task, "termName")}

    out: dict[str, dict] = {}
    for sid, e in acc.items():
        best = e["final"] or e["term"]
        if best is None and not e["in_gpa"]:
            continue
        graded_terms = len([t for t in e["term_ids"] if t is not None])
        out[sid] = {
            "grade_pct": best["pct"] if best else None,
            "grade_letter": best["letter"] if best else None,
            "term": best["term"] if best else None,
            "final_pct": e["final"]["pct"] if e["final"] else None,
            "in_gpa": 1 if e["in_gpa"] else 0,
            "credits": round(graded_terms / e["total_terms"], 2)
                       if graded_terms and e["total_terms"] else None,
        }
    return out


def parse_assignments(detail_json, section_id: str) -> list[dict]:
    """Grade detail for one section -> assignment rows.

    The category name only exists on the enclosing category node, which is why
    this walks the tree by hand instead of scanning for assignment-shaped dicts.
    """
    out: dict[str, dict] = {}
    detail = detail_json if isinstance(detail_json, dict) else {}
    for group in _as_list(detail.get("details")):
        if not isinstance(group, dict):
            continue
        for category in _as_list(group.get("categories")):
            if not isinstance(category, dict):
                continue
            name = _first(category, "name", "groupName")
            for a in _as_list(category.get("assignments")):
                if not isinstance(a, dict) or a.get("dropped"):
                    continue
                cid = _first(a, "objectSectionID", "assignmentID", "id")
                title = _first(a, "assignmentName", "name")
                if cid is None or not title:
                    continue
                due = _first(a, "dueDate", "endDate", "assignedDate")
                out[str(cid)] = {
                    "campus_id": str(cid),
                    "section_id": section_id,
                    "name": str(title),
                    "category": str(name) if name else None,
                    "points": _num(_first(a, "scorePoints", "score")),
                    "total": _num(_first(a, "totalPoints", "pointsPossible")),
                    # "2025-11-01T03:59:00.000Z" -> "2025-11-01". Dates are all the
                    # page and the SQL ever sort or display.
                    "due_at": str(due)[:10] if due else None,
                    "missing": 1 if a.get("missing") in (True, 1, "true", "1") else 0,
                }
    return list(out.values())


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #

def search_district(name: str, state: str, session=None) -> dict:
    """Resolve a district name + state to its portal base URL and app name.

    Only used when CAMPUS_BASE / CAMPUS_APP are unset. This service is flaky.
    """
    s = session or requests.Session()
    try:
        resp = s.get(DISTRICT_SEARCH, params={"query": name, "state": state}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise CampusError(f"district lookup failed ({e.__class__.__name__}); "
                          f"set CAMPUS_BASE and CAMPUS_APP to skip it")
    except ValueError:
        raise CampusError("district lookup returned non-JSON")

    matches = data.get("data") if isinstance(data, dict) else data
    if not matches:
        raise CampusError(f"no district matched {name!r} in {state!r}")
    first = matches[0]
    base = _first(first, "district_baseurl", "districtBaseURL", "baseurl")
    app = _first(first, "district_app_name", "districtAppName", "appName")
    if not base or not app:
        raise CampusError("district record missing base URL or app name")
    return {"base": base if base.endswith("/") else base + "/", "app_name": app}


class Campus:
    """One authenticated portal session. Construct, `login()`, then fetch."""

    def __init__(self, base: str, app_name: str, username: str, password: str, session=None):
        self.base = base if base.endswith("/") else base + "/"
        self.app_name = app_name
        self.username = username
        self.password = password
        self.session = session or requests.Session()
        try:
            self.session.headers["User-Agent"] = USER_AGENT
        except (AttributeError, TypeError):
            pass  # a test double without headers

    def _get(self, path: str):
        try:
            resp = self.session.get(self.base + path.lstrip("/"), timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise CampusError(f"GET {path} failed ({e.__class__.__name__})")
        except ValueError:
            # A portal that wants a login answers with the sign-in HTML, not JSON.
            raise CampusError(f"GET {path} returned non-JSON (session expired?)")

    def login(self) -> None:
        """Authenticate; the session cookie is retained on `self.session`.

        POST, not GET: a requests exception stringifies the whole URL, and that
        string is stored and rendered as the sync status. Credentials in the body
        stay out of it — and out of the district's access log.
        """
        try:
            resp = self.session.post(
                self.base + "verify.jsp",
                data={
                    "nonBrowser": "true",
                    "username": self.username,
                    "password": self.password,
                    "appName": self.app_name,
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            # Exception type only. Never the message: it can carry request detail.
            raise CampusError(f"sign-in request failed ({e.__class__.__name__})")
        if "success" not in resp.text.lower():
            raise CampusError("sign-in rejected")

    def roster(self):
        return self._get("resources/portal/roster")

    def grades(self):
        return self._get("resources/portal/grades")

    def assignments(self, section_id: str):
        """Grade detail: the only portal path that carries assignment rows."""
        return self._get(f"resources/portal/grades/detail/{section_id}")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def redact(text: str) -> str:
    """Strip credential values out of a message before it is stored or displayed.

    Belt to login()'s braces: any future code path that stringifies a request
    still can't leak the password into the sync status line.
    """
    creds = credentials()
    if not creds:
        return text
    for secret in (creds["password"], creds["user"]):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def credentials() -> dict | None:
    """Campus config from env, or None when the integration isn't configured.

    `base`/`app_name` are optional: set them to address the portal directly and
    skip the district-search service entirely. Otherwise district + state are
    required so it can be looked up.
    """
    user = os.environ.get("CAMPUS_USER", "").strip()
    password = os.environ.get("CAMPUS_PASS", "")
    base = os.environ.get("CAMPUS_BASE", "").strip()
    app_name = os.environ.get("CAMPUS_APP", "").strip()
    district = os.environ.get("CAMPUS_DISTRICT", "").strip()
    state = os.environ.get("CAMPUS_STATE", "").strip()
    if not (user and password):
        return None
    if not ((base and app_name) or (district and state)):
        return None
    return {"district": district, "state": state, "user": user, "password": password,
            "base": base, "app_name": app_name}
