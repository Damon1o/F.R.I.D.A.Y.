"""Infinite Campus Student portal client.

Infinite Campus publishes no student API. This talks to the portal's own JSON
endpoints with the student's district credentials — read-only, nothing is ever
written back.

No Flask imports: the parsers are pure functions over decoded JSON, so they are
unit-testable against recorded fixtures with no network.

The endpoints are undocumented and versioned per district, so every parser is
tolerant: it walks the response tree looking for the keys it needs instead of
assuming a fixed shape. A district upgrade that moves a field deeper still works;
one that renames it surfaces as a missing value, not a crash.
"""
import os

import requests

DISTRICT_SEARCH = "https://mobile.infinitecampus.com/api/district/searchDistrict"
TIMEOUT = 20


class CampusError(RuntimeError):
    """Any failure reaching, authenticating to, or decoding Infinite Campus."""


# --------------------------------------------------------------------------- #
# Tree helpers — the portal nests differently per district, so don't assume.
# --------------------------------------------------------------------------- #

def _first(d: dict, *keys, default=None):
    """First present, non-null value among `keys`. Case-sensitive, order matters."""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


SECTION_KEYS = ("sectionID", "sectionId", "_sectionID", "section_id")


def _walk(node, section_id=None):
    """Yield (nearest_section_id, dict) for every dict in the tree.

    A sectionID found on a node applies to that node and everything under it,
    which is how a course's grades and assignments get attributed without
    knowing how deeply the district nests them.
    """
    if isinstance(node, dict):
        sid = _first(node, *SECTION_KEYS, default=section_id)
        sid = str(sid) if sid is not None else None
        yield sid, node
        for v in node.values():
            yield from _walk(v, sid)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, section_id)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Parsers (pure)
# --------------------------------------------------------------------------- #

def parse_courses(roster_json) -> list[dict]:
    """Roster response -> one row per section. Later duplicates lose to earlier."""
    out: dict[str, dict] = {}
    for sid, node in _walk(roster_json):
        if sid is None or sid in out:
            continue
        name = _first(node, "courseName", "name", "sectionName")
        if not name:
            continue
        out[sid] = {
            "section_id": sid,
            "name": str(name),
            "teacher": _first(node, "teacherDisplay", "teacherName", "primaryTeacher"),
            "period": _first(node, "periodName", "periodSequence", "period"),
            "term": _first(node, "termName", "term"),
        }
    return list(out.values())


PERCENT_KEYS = ("progressPercent", "percent", "score", "progressScore")
LETTER_KEYS = ("progressScore", "score", "letterGrade", "gradeLetter")


def parse_grades(grades_json) -> dict[str, dict]:
    """Grades response -> {section_id: {"grade_pct": float|None, "grade_letter": str|None}}.

    Campus reports a percent per grading task; the posted term grade is the one
    that matters. Take the first task that carries a percent for a section and
    ignore the rest, which are progress snapshots of the same number.
    """
    out: dict[str, dict] = {}
    for sid, node in _walk(grades_json):
        if sid is None or sid in out:
            continue
        pct = _num(_first(node, *PERCENT_KEYS))
        if pct is None:
            continue
        letter = _first(node, *LETTER_KEYS)
        out[sid] = {
            "grade_pct": pct,
            "grade_letter": str(letter) if isinstance(letter, str) else None,
        }
    return out


ASSIGNMENT_ID_KEYS = ("objectSectionID", "assignmentID", "id")


def parse_assignments(assignments_json, section_id: str) -> list[dict]:
    """Assignment response for one section -> rows keyed on the Campus object id."""
    out: dict[str, dict] = {}
    for _sid, node in _walk(assignments_json):
        name = _first(node, "assignmentName", "name", "title")
        if not name:
            continue
        cid = _first(node, *ASSIGNMENT_ID_KEYS)
        if cid is None:
            continue
        cid = str(cid)
        if cid in out:
            continue
        out[cid] = {
            "campus_id": cid,
            "section_id": section_id,
            "name": str(name),
            "category": _first(node, "groupName", "categoryName", "group"),
            "points": _num(_first(node, "scorePoints", "score", "pointsEarned")),
            "total": _num(_first(node, "totalPoints", "pointsPossible", "possible")),
            "due_at": _first(node, "dueDate", "endDate", "assignedDate"),
            "missing": 1 if _first(node, "missing", "isMissing") in (True, 1, "true", "1") else 0,
        }
    return list(out.values())


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #

def search_district(name: str, state: str, session=None) -> dict:
    """Resolve a district name + state to its portal base URL and app name."""
    s = session or requests.Session()
    try:
        resp = s.get(DISTRICT_SEARCH, params={"query": name, "state": state}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise CampusError(f"district lookup failed: {e}")
    except ValueError as e:
        raise CampusError(f"district lookup returned non-JSON: {e}")

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

    def _get(self, path: str):
        url = self.base + path.lstrip("/")
        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise CampusError(f"GET {path} failed: {e}")
        except ValueError:
            # A portal that wants a login returns the sign-in HTML page, not JSON.
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
        # verify.jsp answers 200 either way; the body carries the verdict.
        if "success" not in resp.text.lower():
            raise CampusError("sign-in rejected")

    def roster(self):
        return self._get("resources/portal/roster")

    def grades(self):
        return self._get("resources/portal/grades")

    def assignments(self, section_id: str):
        return self._get(f"resources/portal/assignment/section/{section_id}")


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
    """Campus credentials from env, or None when the integration isn't configured."""
    district = os.environ.get("CAMPUS_DISTRICT", "").strip()
    state = os.environ.get("CAMPUS_STATE", "").strip()
    user = os.environ.get("CAMPUS_USER", "").strip()
    password = os.environ.get("CAMPUS_PASS", "")
    if not (district and state and user and password):
        return None
    return {"district": district, "state": state, "user": user, "password": password}
