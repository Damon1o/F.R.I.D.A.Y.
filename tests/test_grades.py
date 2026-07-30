"""Infinite Campus grades: parsing, sync idempotency, ranking, alerts, analysis. No network."""
import json

import pytest

from core import campus
from core.db import execute, query
from pages.grades import models

# --------------------------------------------------------------------------- #
# Fixtures trimmed from real portal responses — same nesting, same field names.
# --------------------------------------------------------------------------- #

ROSTER = [
    {"sectionID": 101, "courseName": "AP Calculus", "courseNumber": "MA300",
     "teacherDisplay": "Smith, J", "roomName": "124",
     "sectionPlacements": [{"sectionID": 101, "termName": "Q1", "termSeq": 1,
                            "periodName": "3", "teacherDisplay": "Smith, J"}]},
    {"sectionID": 202, "courseName": "US History", "courseNumber": "SS210",
     "teacherDisplay": "Doe, A", "roomName": "310",
     "sectionPlacements": [{"sectionID": 202, "termName": "Q1", "termSeq": 1,
                            "periodName": "5", "teacherDisplay": "Doe, A"}]},
    # A section the grades payload never mentions: no grade, no detail fetch.
    {"sectionID": 303, "courseName": "Study Hall", "teacherDisplay": "Roe, B",
     "sectionPlacements": []},
]


def _task(pct_earned, pct_total, score):
    return {"taskName": "MP", "taskID": 1, "termID": 805, "termName": "Q1", "termSeq": 1,
            "hasAssignments": True, "includedInTermGPA": True, "usePercent": False,
            "score": score, "progressScore": score,
            "progressPointsEarned": pct_earned, "progressTotalPoints": pct_total}


# One future-year enrollment with terms: null (must be skipped) and one live one.
GRADES = [
    {"enrollmentID": 1, "displayName": "26-27 High School", "gradesEnabled": False,
     "terms": None},
    {"enrollmentID": 2, "displayName": "25-26 High School", "gradesEnabled": True,
     "terms": [
         {"termID": 805, "termName": "Q1", "termSeq": 1, "courses": [
             {"sectionID": 101, "courseName": "AP Calculus", "dropped": False,
              "gradingTasks": [_task(29.0, 40.0, "72")]},
             {"sectionID": 202, "courseName": "US History", "dropped": False,
              "gradingTasks": [_task(47.0, 50.0, "94")]},
         ]},
     ]},
]


def _assignment(oid, name, points, total, due, missing=False):
    return {"objectSectionID": oid, "assignmentName": name, "sectionID": 101,
            "taskID": 1, "termIDs": [805], "dueDate": due + "T03:59:00.000Z",
            "assignedDate": due + "T04:00:00.000Z", "scoringType": "p",
            "score": points, "scorePoints": points, "scorePercentage": None,
            "totalPoints": total, "active": True, "dropped": False,
            "missing": missing, "late": False, "notGraded": False}


# resources/portal/grades/detail/<sectionID>: details[] -> categories[] -> assignments[]
DETAIL = {
    "101": {"terms": [{"termID": 805, "termName": "Q1"}], "details": [
        {"task": {"taskName": "MP", "termID": 805, "sectionID": 948206},
         "categories": [
             {"groupID": 1, "name": "Test", "weight": 60.0, "assignments": [
                 _assignment(1, "Limits quiz", "12.0", 20, "2026-07-10")]},
             {"groupID": 2, "name": "Homework", "weight": 20.0, "assignments": [
                 _assignment(2, "Derivatives set", "9.0", 10, "2026-07-12"),
                 _assignment(3, "Chain rule set", None, 10, "2026-07-20", missing=True),
                 # Dropped rows must not reach the database.
                 dict(_assignment(9, "Voided worksheet", "0", 10, "2026-07-01"),
                      dropped=True)]},
         ]}]},
    "202": {"terms": [{"termID": 805, "termName": "Q1"}], "details": [
        {"task": {"taskName": "MP", "termID": 805},
         "categories": [
             {"groupID": 3, "name": "Project", "assignments": [
                 _assignment(4, "Essay 1", "0", 50, "2026-07-14")]},
         ]}]},
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
        return DETAIL.get(str(section_id), {})


@pytest.fixture
def campus_stub(monkeypatch):
    for k, v in (("CAMPUS_DISTRICT", "Testville"), ("CAMPUS_STATE", "NY"),
                 ("CAMPUS_USER", "student"), ("CAMPUS_PASS", "secret")):
        monkeypatch.setenv(k, v)
    # Independent of the developer's own .env: tests own the whole config.
    for k in ("CAMPUS_BASE", "CAMPUS_APP"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(campus, "search_district",
                        lambda *a, **k: {"base": "https://x.infinitecampus.org/campus/",
                                         "app_name": "testville"})
    monkeypatch.setattr(campus, "Campus", FakeCampus)


# --------------------------------------------------------------------------- #
# 1. Client parsing
# --------------------------------------------------------------------------- #

def test_parse_courses_reads_period_from_section_placements():
    courses = {c["section_id"]: c for c in campus.parse_courses(ROSTER)}
    assert set(courses) == {"101", "202", "303"}
    assert courses["101"]["name"] == "AP Calculus"
    assert courses["101"]["teacher"] == "Smith, J"
    assert courses["101"]["period"] == "3"
    assert courses["101"]["term"] == "Q1"
    assert courses["303"]["period"] is None  # no placements, still a valid row


def _named_task(task_name, score, earned=None, total=None, in_gpa=None):
    return {"taskName": task_name, "taskID": 1, "termID": 808, "termName": "Q4",
            "termSeq": 4, "score": score, "progressScore": score,
            "includedInTermGPA": in_gpa,
            "progressPointsEarned": earned, "progressTotalPoints": total}


# A real Q4: the posted course grade sits alongside a Regents score and the
# running marking-period grade.
YEAR_END = [
    {"enrollmentID": 2, "gradesEnabled": True, "terms": [
        {"termID": 805, "termName": "Q1", "termSeq": 1, "courses": [
            {"sectionID": 101, "courseName": "Biology H", "gradingTasks": [
                _named_task("MP", "96", 2822.0, 2900.0, in_gpa=True)]},
            {"sectionID": 404, "courseName": "Phys. Ed. 9", "gradingTasks": [
                _named_task("MP", "100", 500.0, 500.0)]},
            {"sectionID": 505, "courseName": "STEAM Comp Sci", "gradingTasks": [
                _named_task("MP", "100", 100.0, 100.0, in_gpa=True)]},
        ]},
        {"termID": 806, "termName": "Q2", "termSeq": 2, "courses": [
            {"sectionID": 101, "courseName": "Biology H", "gradingTasks": [
                _named_task("MP", "99", 990.0, 1000.0, in_gpa=True)]},
            {"sectionID": 505, "courseName": "STEAM Comp Sci", "gradingTasks": [
                _named_task("MP", "100", 100.0, 100.0, in_gpa=True),
                _named_task("Final Grade", "100", 100.0, 100.0)]},
        ]},
        {"termID": 807, "termName": "Q3", "termSeq": 3, "courses": [
            {"sectionID": 101, "courseName": "Biology H", "gradingTasks": [
                _named_task("MP", "100", 1000.0, 1000.0, in_gpa=True)]},
        ]},
        {"termID": 808, "termName": "Q4", "termSeq": 4, "courses": [
            {"sectionID": 101, "courseName": "Biology H", "gradingTasks": [
                _named_task("MP", "100", 1000.0, 1000.0, in_gpa=True),
                _named_task("Regents", "89"),
                _named_task("Final Grade", "98", 2822.0, 2900.0)]},
            {"sectionID": 404, "courseName": "Phys. Ed. 9", "gradingTasks": [
                _named_task("Final Grade", "100", 500.0, 500.0)]},
        ]},
    ]},
]


def test_posted_final_grade_beats_the_regents_and_the_marking_period():
    g = campus.parse_grades(YEAR_END)["101"]
    # 98 is posted; 89 is the Regents; 100 is Q4 marking period; 97.31 is the
    # unrounded gradebook ratio. The report card says 98.
    assert g["final_pct"] == pytest.approx(98.0)
    assert g["grade_pct"] == pytest.approx(98.0)


def test_courses_campus_excludes_from_gpa_stay_excluded():
    g = campus.parse_grades(YEAR_END)
    assert g["101"]["in_gpa"] == 1
    assert g["404"]["in_gpa"] == 0     # Phys. Ed.: no includedInTermGPA anywhere


def test_credits_track_the_share_of_the_year_a_course_ran():
    g = campus.parse_grades(YEAR_END)
    assert g["101"]["credits"] == pytest.approx(1.0)   # 4 of 4 marking periods
    assert g["505"]["credits"] == pytest.approx(0.5)   # 2 of 4: a semester course


def test_parse_grades_uses_points_not_the_posted_mark():
    grades = campus.parse_grades(GRADES)
    assert set(grades) == {"101", "202"}          # terms: null enrollment skipped
    assert grades["101"]["grade_pct"] == pytest.approx(72.5)   # 29/40, not score "72"
    assert grades["101"]["grade_letter"] is None   # numeric mark isn't a letter
    assert grades["101"]["term"] == "Q1"


def test_parse_grades_keeps_the_letter_on_a_letter_scale():
    letter = json.loads(json.dumps(GRADES))
    task = letter[1]["terms"][0]["courses"][0]["gradingTasks"][0]
    task["score"] = task["progressScore"] = "C-"
    assert campus.parse_grades(letter)["101"]["grade_letter"] == "C-"


def test_parse_grades_prefers_the_latest_graded_term():
    two_terms = json.loads(json.dumps(GRADES))
    q2 = json.loads(json.dumps(two_terms[1]["terms"][0]))
    q2.update(termID=806, termName="Q2", termSeq=2)
    q2["courses"] = [q2["courses"][0]]
    q2["courses"][0]["gradingTasks"] = [_task(30.0, 50.0, "60")]
    two_terms[1]["terms"].append(q2)
    grades = campus.parse_grades(two_terms)
    assert grades["101"]["grade_pct"] == pytest.approx(60.0)
    assert grades["101"]["term"] == "Q2"


def test_parse_assignments_takes_the_category_from_its_parent():
    rows = campus.parse_assignments(DETAIL["101"], "101")
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"Limits quiz", "Derivatives set", "Chain rule set"}
    assert by_name["Limits quiz"]["category"] == "Test"
    assert by_name["Limits quiz"]["points"] == 12
    assert by_name["Limits quiz"]["due_at"] == "2026-07-10"   # date, not ISO instant
    assert by_name["Derivatives set"]["category"] == "Homework"
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
    assert first["courses"] == 3
    models.sync(force=True)  # same fixture, second time

    assert query("SELECT count(*) AS n FROM courses", one=True)["n"] == 3
    assert query("SELECT count(*) AS n FROM assignments", one=True)["n"] == 4
    # Study Hall has no grade, so no history row and no detail fetch.
    assert query("SELECT count(*) AS n FROM grade_history", one=True)["n"] == 2


def test_history_row_only_on_change(ctx, campus_stub, monkeypatch):
    models.sync(force=True)
    assert query("SELECT count(*) AS n FROM grade_history WHERE section_id = '101'",
                 one=True)["n"] == 1

    bumped = json.loads(json.dumps(GRADES))
    bumped[1]["terms"][0]["courses"][0]["gradingTasks"][0]["progressPointsEarned"] = 27.2
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
    assert query("SELECT count(*) AS n FROM courses", one=True)["n"] == 3
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
    for k in ("CAMPUS_DISTRICT", "CAMPUS_STATE", "CAMPUS_USER", "CAMPUS_PASS",
              "CAMPUS_BASE", "CAMPUS_APP"):
        monkeypatch.delenv(k, raising=False)
    assert models.sync(force=True)["configured"] is False


def test_explicit_base_skips_the_district_search_service(ctx, campus_stub, monkeypatch):
    """searchDistrict answers 504 for long stretches; CAMPUS_BASE must bypass it."""
    def never(*_a, **_k):
        raise AssertionError("search_district was called despite CAMPUS_BASE")

    monkeypatch.setattr(campus, "search_district", never)
    monkeypatch.setenv("CAMPUS_BASE", "https://x.infinitecampus.org/campus/")
    monkeypatch.setenv("CAMPUS_APP", "testville")
    assert models.sync(force=True)["error"] is None


def test_district_search_is_used_when_base_is_absent(ctx, campus_stub, monkeypatch):
    monkeypatch.delenv("CAMPUS_BASE", raising=False)
    monkeypatch.delenv("CAMPUS_APP", raising=False)
    calls = []
    monkeypatch.setattr(campus, "search_district",
                        lambda *a, **k: calls.append(a) or
                        {"base": "https://x.infinitecampus.org/campus/", "app_name": "t"})
    assert models.sync(force=True)["error"] is None
    assert len(calls) == 1


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


def test_extra_credit_never_reports_negative_points_lost(ctx, campus_stub):
    models.sync(force=True)
    execute("UPDATE assignments SET points = 25, total = 20 WHERE name = 'Limits quiz'")
    calc = next(c for c in models.weakest_courses() if c["name"] == "AP Calculus")
    assert calc["points_lost"] == pytest.approx(1.0)  # the homework point, not -4


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

def test_configured_page_renders_the_ranking(ctx, campus_stub, client):
    models.sync(force=True)
    html = client.get("/grades").get_data(as_text=True)
    assert "Weakest courses" in html
    assert "AP Calculus" in html
    assert "Connect Infinite Campus" not in html


def test_nav_has_both_educational_links(client):
    html = client.get("/notes").get_data(as_text=True)
    assert 'href="/grades"' in html
    assert 'href="/sat"' in html
    assert "Educational" in html


def test_pages_render_without_campus_configured(client, monkeypatch):
    for k in ("CAMPUS_DISTRICT", "CAMPUS_STATE", "CAMPUS_USER", "CAMPUS_PASS",
              "CAMPUS_BASE", "CAMPUS_APP"):
        monkeypatch.delenv(k, raising=False)
    grades = client.get("/grades")
    assert grades.status_code == 200
    assert "Connect Infinite Campus" in grades.get_data(as_text=True)
    assert client.get("/sat").status_code == 200
