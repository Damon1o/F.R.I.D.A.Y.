"""Infinite Campus grades: parsing, sync idempotency, ranking, alerts, analysis. No network."""
import json

import pytest

from core import campus
from core.db import execute, query
from pages.grades import models

# --------------------------------------------------------------------------- #
# Recorded-shape fixtures (nested the way the portal nests them)
# --------------------------------------------------------------------------- #

ROSTER = [
    {"sectionID": 101, "courseName": "AP Calculus", "teacherDisplay": "Smith, J",
     "periodName": "3", "termName": "S1"},
    {"sectionID": 202, "courseName": "US History", "teacherDisplay": "Doe, A",
     "periodName": "5", "termName": "S1"},
]

GRADES = [
    {"sectionID": 101, "terms": [{"gradingTasks": [
        {"taskName": "Term Grade", "progressPercent": 72.5, "progressScore": "C-"}]}]},
    {"sectionID": 202, "terms": [{"gradingTasks": [
        {"taskName": "Term Grade", "progressPercent": 94.0, "progressScore": "A"}]}]},
]

ASSIGNMENTS = {
    "101": [
        {"objectSectionID": 1, "assignmentName": "Limits quiz", "groupName": "Test",
         "scorePoints": 12, "totalPoints": 20, "dueDate": "2026-07-10", "missing": False},
        {"objectSectionID": 2, "assignmentName": "Derivatives set", "groupName": "Homework",
         "scorePoints": 9, "totalPoints": 10, "dueDate": "2026-07-12", "missing": False},
        {"objectSectionID": 3, "assignmentName": "Chain rule set", "groupName": "Homework",
         "scorePoints": None, "totalPoints": 10, "dueDate": "2026-07-20", "missing": True},
    ],
    "202": [
        {"objectSectionID": 4, "assignmentName": "Essay 1", "groupName": "Project",
         "scorePoints": 0, "totalPoints": 50, "dueDate": "2026-07-14", "missing": False},
    ],
}


class FakeCampus:
    """Stands in for core.campus.Campus — same surface, zero network."""

    def __init__(self, *_a, **_k):
        self.logged_in = False

    def login(self):
        self.logged_in = True

    def roster(self):
        return ROSTER

    def grades(self):
        return GRADES

    def assignments(self, section_id):
        return ASSIGNMENTS.get(str(section_id), [])


@pytest.fixture
def campus_stub(monkeypatch):
    for k, v in (("CAMPUS_DISTRICT", "Testville"), ("CAMPUS_STATE", "NY"),
                 ("CAMPUS_USER", "student"), ("CAMPUS_PASS", "secret")):
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(campus, "search_district",
                        lambda *a, **k: {"base": "https://x.infinitecampus.org/campus/",
                                         "app_name": "testville"})
    monkeypatch.setattr(campus, "Campus", FakeCampus)


# --------------------------------------------------------------------------- #
# 1. Client parsing
# --------------------------------------------------------------------------- #

def test_parsers_read_nested_fixtures():
    courses = campus.parse_courses(ROSTER)
    assert {c["section_id"] for c in courses} == {"101", "202"}
    assert courses[0]["name"] == "AP Calculus"
    assert courses[0]["teacher"] == "Smith, J"

    grades = campus.parse_grades(GRADES)
    assert grades["101"] == {"grade_pct": 72.5, "grade_letter": "C-"}

    rows = campus.parse_assignments(ASSIGNMENTS["101"], "101")
    assert len(rows) == 3
    by_name = {r["name"]: r for r in rows}
    assert by_name["Limits quiz"]["category"] == "Test"
    assert by_name["Limits quiz"]["points"] == 12
    assert by_name["Chain rule set"]["missing"] == 1
    assert by_name["Chain rule set"]["points"] is None


def test_credentials_absent_is_not_an_error(monkeypatch):
    for k in ("CAMPUS_DISTRICT", "CAMPUS_STATE", "CAMPUS_USER", "CAMPUS_PASS"):
        monkeypatch.delenv(k, raising=False)
    assert campus.credentials() is None


# --------------------------------------------------------------------------- #
# 2 & 3. Sync: idempotency and change-only history
# --------------------------------------------------------------------------- #

def test_sync_is_idempotent(ctx, campus_stub):
    first = models.sync(force=True)
    assert first["error"] is None
    assert first["courses"] == 2
    models.sync(force=True)  # same fixture, second time

    assert query("SELECT count(*) AS n FROM courses", one=True)["n"] == 2
    assert query("SELECT count(*) AS n FROM assignments", one=True)["n"] == 4
    assert query("SELECT count(*) AS n FROM grade_history", one=True)["n"] == 2


def test_history_row_only_on_change(ctx, campus_stub, monkeypatch):
    models.sync(force=True)
    assert query("SELECT count(*) AS n FROM grade_history WHERE section_id = '101'",
                 one=True)["n"] == 1

    monkeypatch.setitem(ASSIGNMENTS, "101", ASSIGNMENTS["101"])  # unchanged
    bumped = json.loads(json.dumps(GRADES))
    bumped[0]["terms"][0]["gradingTasks"][0]["progressPercent"] = 68.0
    monkeypatch.setattr(FakeCampus, "grades", lambda self: bumped)
    models.sync(force=True)

    rows = query("SELECT grade_pct FROM grade_history WHERE section_id = '101' "
                 "ORDER BY id")
    assert [r["grade_pct"] for r in rows] == [72.5, 68.0]


def test_sync_throttles_and_failure_keeps_cached_data(ctx, campus_stub, monkeypatch):
    models.sync(force=True)
    assert models.sync()["ran"] is False  # inside the 2h window

    def boom(self):
        raise campus.CampusError("sign-in rejected")

    monkeypatch.setattr(FakeCampus, "login", boom)
    result = models.sync(force=True)
    assert result["error"] == "sign-in rejected"
    assert query("SELECT count(*) AS n FROM courses", one=True)["n"] == 2
    assert models.status()["error"] == "sign-in rejected"


def test_sync_error_never_leaks_credentials(ctx, campus_stub, monkeypatch):
    """A requests exception stringifies the URL; the password must not survive it."""
    def leaky(self):
        raise campus.requests.ConnectionError(
            "HTTPSConnectionPool: /campus/verify.jsp?username=student&password=secret"
        )

    monkeypatch.setattr(FakeCampus, "login", leaky)
    result = models.sync(force=True)
    assert "secret" not in result["error"]
    assert "student" not in result["error"]
    assert "[redacted]" in result["error"]
    assert "secret" not in models.status()["error"]


def test_login_sends_credentials_in_the_body_not_the_url():
    sent = {}

    class Recorder:
        def post(self, url, data=None, timeout=None):
            sent.update(url=url, data=data)

            class R:
                text = "success"

                def raise_for_status(self):
                    pass
            return R()

    campus.Campus("https://x.infinitecampus.org/campus/", "app", "student", "secret",
                  session=Recorder()).login()
    assert "secret" not in sent["url"]
    assert sent["data"]["password"] == "secret"


def test_sync_reports_unconfigured(ctx, monkeypatch):
    for k in ("CAMPUS_DISTRICT", "CAMPUS_STATE", "CAMPUS_USER", "CAMPUS_PASS"):
        monkeypatch.delenv(k, raising=False)
    assert models.sync(force=True)["configured"] is False


# --------------------------------------------------------------------------- #
# 4. Ranking SQL
# --------------------------------------------------------------------------- #

def test_ranking_puts_the_weakest_first(ctx, campus_stub):
    models.sync(force=True)
    r = models.ranking()

    assert r["courses"][0]["name"] == "AP Calculus"     # 72.5 before 94.0
    assert r["courses"][0]["points_lost"] == pytest.approx(9.0)  # 8 on the quiz + 1 on homework

    # Project is 0/50; Test is 12/20 (60%); Homework is 9/10 (90%).
    assert [k["category"] for k in r["categories"]] == ["Project", "Test", "Homework"]
    assert r["categories"][1]["pct"] == pytest.approx(60.0)


# --------------------------------------------------------------------------- #
# 5. Alerts
# --------------------------------------------------------------------------- #

def test_alerts_flag_missing_zero_and_drop(ctx, campus_stub):
    models.sync(force=True)
    execute("INSERT INTO grade_history (section_id, grade_pct, recorded_at) VALUES "
            "('101', 80.0, %s)", (models._stamp(models._utcnow() - models.timedelta(days=3)),))

    a = models.alerts()
    assert [x["name"] for x in a["missing"]] == ["Chain rule set"]
    assert [x["name"] for x in a["zeros"]] == ["Essay 1"]
    drops = {d["course"]: d for d in a["drops"]}
    assert "AP Calculus" in drops
    assert drops["AP Calculus"]["drop_pts"] == pytest.approx(7.5)


def test_drop_below_threshold_is_not_an_alert(ctx, campus_stub):
    models.sync(force=True)
    execute("INSERT INTO grade_history (section_id, grade_pct, recorded_at) VALUES "
            "('101', 73.5, %s)", (models._stamp(models._utcnow() - models.timedelta(days=1)),))
    assert models.alerts()["drops"] == []


# --------------------------------------------------------------------------- #
# 6. Analysis endpoint: stub LLM + cache by ranking hash
# --------------------------------------------------------------------------- #

class StubLLM:
    calls = 0

    def __init__(self):
        self.api_key = "test"

    def complete(self, messages, tools=None):
        StubLLM.calls += 1
        return {"role": "assistant", "content": "Calculus is the leak.\nThis week: redo the limits quiz."}


def test_analysis_caches_until_the_ranking_changes(ctx, campus_stub):
    models.sync(force=True)
    StubLLM.calls = 0

    first = models.analysis(client=StubLLM())
    assert "Calculus is the leak" in first["text"]
    assert first["cached"] is False
    assert StubLLM.calls == 1

    second = models.analysis(client=StubLLM())
    assert second["cached"] is True
    assert StubLLM.calls == 1  # same ranking hash: no second LLM call

    execute("UPDATE courses SET grade_pct = 50 WHERE section_id = '101'")
    third = models.analysis(client=StubLLM())
    assert third["cached"] is False
    assert StubLLM.calls == 2


def test_analysis_without_a_key_reports_not_configured(ctx, campus_stub):
    models.sync(force=True)

    class NoKey(StubLLM):
        def __init__(self):
            self.api_key = ""

    result = models.analysis(client=NoKey())
    assert result["configured"] is False
    assert result["text"] is None


def test_analysis_endpoint_400s_with_no_data(client):
    assert client.post("/api/grades/analysis").status_code == 400


# --------------------------------------------------------------------------- #
# 7. Navigation
# --------------------------------------------------------------------------- #

def test_nav_has_both_educational_links(client):
    html = client.get("/notes").get_data(as_text=True)
    assert 'href="/grades"' in html
    assert 'href="/sat"' in html
    assert "Educational" in html


def test_pages_render_without_campus_configured(client, monkeypatch):
    for k in ("CAMPUS_DISTRICT", "CAMPUS_STATE", "CAMPUS_USER", "CAMPUS_PASS"):
        monkeypatch.delenv(k, raising=False)
    grades = client.get("/grades")
    assert grades.status_code == 200
    assert "Connect Infinite Campus" in grades.get_data(as_text=True)
    assert client.get("/sat").status_code == 200
