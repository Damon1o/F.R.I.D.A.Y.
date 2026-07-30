"""GPA computed locally: level detection, both credit models, accuracy check."""
import pytest

from core.db import execute
from pages.calendar.models import ValidationError
from pages.grades import gpa, models

# The real 9th-grade year: posted finals, five honors courses, two semester
# courses, and a Phys. Ed. that Campus excludes from the GPA.
YEAR_9 = [
    ("Mandarin 2H", 100, "honors", 1.0),
    ("STEAM Comp Sci", 100, "regular", 0.5),
    ("STEAM Research", 100, "regular", 0.5),
    ("Design/Draw - Prod", 99, "regular", 1.0),
    ("Global Hist & Geog 1 H", 98, "honors", 1.0),
    ("Biology H", 98, "honors", 1.0),
    ("Geometry H", 97, "honors", 1.0),
    ("English 1 H", 96, "honors", 1.0),
]


@pytest.fixture
def year9(ctx):
    """Seed the courses table the way a sync would."""
    for i, (name, final, level, credits) in enumerate(YEAR_9):
        execute(
            "INSERT INTO courses (section_id, name, grade_pct, final_pct, in_gpa, credits, "
            "level, synced_at) VALUES (%s, %s, %s, %s, 1, %s, %s, '2026-07-29 00:00:00')",
            (str(900 + i), name, final, final, credits, level),
        )
    execute(
        "INSERT INTO courses (section_id, name, grade_pct, final_pct, in_gpa, credits, level, "
        "synced_at) VALUES ('999', 'Phys. Ed. 9', 100, 100, 0, 1, 'regular', "
        "'2026-07-29 00:00:00')"
    )


# --------------------------------------------------------------------------- #
# Level detection
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,expected", [
    # Campus abbreviations
    ("Biology H", "honors"),
    ("Mandarin 2H", "honors"),
    ("English 1H-Fresh Sem", "honors"),
    ("Global Hist & Geog 1 H", "honors"),
    # Catalog spellings, and the two other +2 categories the catalog names
    ("ENGLISH 1 Honors", "honors"),
    ("College Pre-Calculus Honors", "honors"),
    ("Accelerated Chemistry", "honors"),
    ("ADVANCED DRAWING AND PAINTING", "honors"),
    ("Advanced Sculpture", "honors"),
    # +5: "Advanced Placement" wins over the "Advanced" in it
    ("AP Calculus BC", "ap"),
    ("ADVANCED PLACEMENT ART AND DESIGN", "ap"),
    ("Advanced Placement Computer Science A", "ap"),
    # Unweighted
    ("Design/Draw - Prod", "regular"),
    ("STEAM Comp Sci", "regular"),
    ("Phys. Ed. 9", "regular"),
    ("Lunch 9", "regular"),
    ("", "regular"),
])
def test_detect_level(name, expected):
    assert gpa.detect_level(name) == expected


def test_bonus_scale_matches_the_published_catalog():
    """Catalog of Courses, Student Transcripts: AP 5 points added,
    Honors/Accelerated/Advanced 2 points added."""
    assert gpa.BONUS == {"regular": 0.0, "honors": 2.0, "ap": 5.0}


# --------------------------------------------------------------------------- #
# Level overrides
# --------------------------------------------------------------------------- #

def test_pinned_level_beats_detection_and_moves_the_gpa(year9):
    before = gpa.compute()["weighted"]
    gpa.set_level("Design/Draw - Prod", "ap")     # regular -> +5
    after = gpa.compute()
    assert after["weighted"] == pytest.approx(before + 5 / 8)
    row = next(c for c in after["courses"] if c["name"] == "Design/Draw - Prod")
    assert (row["level"], row["detected"], row["pinned"]) == ("ap", "regular", True)


def test_auto_clears_the_pin(year9):
    gpa.set_level("Design/Draw - Prod", "ap")
    assert gpa.set_level("Design/Draw - Prod", "auto") is None
    assert gpa.compute()["weighted"] == pytest.approx(99.75)


def test_pin_survives_a_resync(year9):
    gpa.set_level("Design/Draw - Prod", "honors")
    # A sync rewrites courses.level from detection; the pin is a separate table.
    execute("UPDATE courses SET level = 'regular' WHERE name = 'Design/Draw - Prod'")
    row = next(c for c in gpa.compute()["courses"] if c["name"] == "Design/Draw - Prod")
    assert row["level"] == "honors"


def test_set_level_rejects_bad_input(ctx):
    with pytest.raises(ValidationError):
        gpa.set_level("", "ap")
    with pytest.raises(ValidationError):
        gpa.set_level("Biology H", "superhonors")


def test_level_api(client, year9):
    r = client.post("/api/gpa/level", json={"name": "Design/Draw - Prod", "level": "ap"})
    assert r.status_code == 200
    assert r.get_json()["gpa"]["weighted"] == pytest.approx(99.75 + 5 / 8)
    assert client.post("/api/gpa/level", json={"name": "X", "level": "bogus"}).status_code == 400


# --------------------------------------------------------------------------- #
# The four numbers
# --------------------------------------------------------------------------- #

def test_gpa_excludes_courses_campus_excludes(year9):
    result = gpa.compute()
    assert result["count"] == 8
    assert "Phys. Ed. 9" not in {c["name"] for c in result["courses"]}


def test_unweighted_and_weighted_equal_credit(year9):
    result = gpa.compute()
    # 100+100+100+99+98+98+97+96 = 788, over 8 courses.
    assert result["unweighted"] == pytest.approx(98.50)
    # Five honors courses at +2 each: 798 over 8.
    assert result["weighted"] == pytest.approx(99.75)


def test_credit_scaled_models(year9):
    result = gpa.compute()
    assert result["credits"] == pytest.approx(7.0)   # six full-year, two half
    assert result["unweighted_credited"] == pytest.approx(688 / 7)
    assert result["weighted_credited"] == pytest.approx(698 / 7)


def test_ap_earns_five_points(ctx):
    execute("INSERT INTO courses (section_id, name, final_pct, in_gpa, credits, level, "
            "synced_at) VALUES ('1', 'AP Calculus BC', 90, 1, 1, 'ap', '2026-07-29 00:00:00')")
    result = gpa.compute()
    assert result["ap"] == 1
    assert result["unweighted"] == pytest.approx(90.0)
    assert result["weighted"] == pytest.approx(95.0)


def test_empty_gpa_is_none_not_a_crash(ctx):
    result = gpa.compute()
    assert result["count"] == 0
    assert result["unweighted"] is None
    assert result["weighted"] is None


# --------------------------------------------------------------------------- #
# Accuracy check against the official number
# --------------------------------------------------------------------------- #

def test_compare_ranks_the_matching_model_first(year9):
    ranked = gpa.compare(98.50)
    assert ranked[0]["model"] == "Unweighted, equal credit"
    assert ranked[0]["delta"] == 0
    assert all(abs(m["delta"]) >= abs(ranked[0]["delta"]) for m in ranked)


def test_compare_without_an_official_number_still_reports_values(year9):
    ranked = gpa.compare(None)
    assert len(ranked) == 4
    assert all(m["delta"] is None for m in ranked)
    assert all(m["value"] is not None for m in ranked)


def test_official_gpa_round_trips(ctx):
    assert models.official_gpa() is None
    models.set_official_gpa("98.5")
    assert models.official_gpa() == pytest.approx(98.5)
    models.set_official_gpa(None)
    assert models.official_gpa() is None


# --------------------------------------------------------------------------- #
# Hand-entered years: the GPA starts in 8th grade, which Campus will not serve
# --------------------------------------------------------------------------- #

def test_manual_years_join_the_calculation(year9):
    gpa.add_manual("Grade 8", "Algebra 1 H", 95, "honors", 1)
    gpa.add_manual("Grade 8", "Earth Science", 90, "regular", 1)
    result = gpa.compute()
    assert result["count"] == 10
    assert result["unweighted"] == pytest.approx((788 + 95 + 90) / 10)
    # Honors bonus applies to the hand-entered course too: six honors now.
    assert result["weighted"] == pytest.approx((798 + 97 + 90) / 10)
    years = {y["year"]: y for y in result["years"]}
    assert set(years) == {"current", "Grade 8"}
    assert years["Grade 8"]["unweighted"] == pytest.approx(92.5)


def test_manual_course_can_be_removed(ctx):
    row = gpa.add_manual("Grade 8", "Algebra 1 H", 95, "honors", 1)
    assert gpa.delete_manual(row["id"]) is True
    assert gpa.delete_manual(row["id"]) is False
    assert gpa.compute()["count"] == 0


@pytest.mark.parametrize("kwargs", [
    {"year": "", "name": "X", "final_pct": 90},
    {"year": "Grade 8", "name": "", "final_pct": 90},
    {"year": "Grade 8", "name": "X", "final_pct": "abc"},
    {"year": "Grade 8", "name": "X", "final_pct": 900},
    {"year": "Grade 8", "name": "X", "final_pct": -1},
    {"year": "Grade 8", "name": "X", "final_pct": 90, "level": "superhonors"},
    {"year": "Grade 8", "name": "X", "final_pct": 90, "credits": 0},
])
def test_manual_entry_rejects_bad_input(ctx, kwargs):
    with pytest.raises(ValidationError):
        gpa.add_manual(**kwargs)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def test_gpa_api_returns_models_and_official(client):
    body = client.get("/api/gpa").get_json()
    assert set(body) == {"gpa", "official", "models"}
    assert len(body["models"]) == 4


def test_gpa_course_api_round_trip(client):
    created = client.post("/api/gpa/courses", json={
        "year": "Grade 8", "name": "Algebra 1 H", "final_pct": 95,
        "level": "honors", "credits": 1})
    assert created.status_code == 201
    row_id = created.get_json()["id"]
    assert client.get("/api/gpa").get_json()["gpa"]["count"] == 1
    assert client.delete(f"/api/gpa/courses/{row_id}").status_code == 204
    assert client.delete(f"/api/gpa/courses/{row_id}").status_code == 404


def test_gpa_course_api_rejects_bad_input(client):
    r = client.post("/api/gpa/courses", json={"year": "Grade 8", "name": "X",
                                             "final_pct": "abc"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_official_gpa_api(client):
    r = client.post("/api/gpa/official", json={"official": 98.5})
    assert r.status_code == 200
    assert r.get_json()["official"] == pytest.approx(98.5)
    assert client.post("/api/gpa/official", json={"official": "nope"}).status_code == 400


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

def test_grades_page_shows_gpa_and_drops_the_category_tables(client, year9):
    html = client.get("/grades").get_data(as_text=True)
    assert "98.50" in html and "99.75" in html
    assert "Weakest courses" in html
    assert "Weakest kinds of classwork" not in html
    assert "By course and category" not in html
