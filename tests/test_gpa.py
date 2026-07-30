"""GPA computed locally: level detection, both credit models, accuracy check."""
import pytest

from core.db import execute
from pages.calendar.models import ValidationError
from pages.grades import gpa, models

# Straight off the official Mepham transcript generated 2026-07-29. Course, Mark,
# Weight — the transcript's own three columns.
YEAR_9 = [
    ("Mandarin 2H", 100, 1.0),
    ("STEAM Comp Sci", 100, 0.25),
    ("STEAM Research", 100, 0.25),
    ("Design/Draw - Prod", 99, 1.0),
    ("Global Hist & Geog 1 H", 98, 1.0),
    ("Biology H", 98, 1.0),
    ("Geometry H", 97, 1.0),
    ("English 1 H", 96, 1.0),
]
GRADE_8 = [("Algebra 1A", 95, "honors", 1.0),      # Regents Algebra taken in 8th
           ("Mandarin I-8", 99, "regular", 1.0),
           ("PS: Earth Science A", 96, "honors", 1.0)]

# Transcript Statistics, verbatim.
OFFICIAL = {"weighted": 99.1579, "unweighted": 97.6842}

# Grade 9 alone: sum(weight) 6.5, sum(mark*weight) 638, bonus 10.
Y9_WEIGHT, Y9_MARKS, Y9_BONUS = 6.5, 638, 10


@pytest.fixture
def year9(ctx):
    """Seed the courses table the way a sync would, with transcript weights."""
    for i, (name, final, weight) in enumerate(YEAR_9):
        execute(
            "INSERT INTO courses (section_id, name, grade_pct, final_pct, in_gpa, credits, "
            "level, synced_at) VALUES (%s, %s, %s, %s, 1, %s, %s, '2026-07-29 00:00:00')",
            (str(900 + i), name, final, final, weight, gpa.detect_level(name)),
        )
    # Phys. Ed. prints 0.500 credit against Weight 0.0000; Campus flags it out.
    execute(
        "INSERT INTO courses (section_id, name, grade_pct, final_pct, in_gpa, credits, level, "
        "synced_at) VALUES ('999', 'Phys. Ed. 9', 100, 100, 0, 0.5, 'regular', "
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
    gpa.set_level("Design/Draw - Prod", "ap")     # regular -> +5, weight 1
    after = gpa.compute()
    assert after["weighted"] == pytest.approx((Y9_MARKS + Y9_BONUS + 5) / Y9_WEIGHT)
    row = next(c for c in after["courses"] if c["name"] == "Design/Draw - Prod")
    assert (row["level"], row["detected"], row["level_pinned"]) == ("ap", "regular", True)


def test_auto_clears_the_pin(year9):
    gpa.set_level("Design/Draw - Prod", "ap")
    assert gpa.set_level("Design/Draw - Prod", "auto") is None
    assert gpa.compute()["weighted"] == pytest.approx((Y9_MARKS + Y9_BONUS) / Y9_WEIGHT)


# --------------------------------------------------------------------------- #
# Weight pins: the transcript's Weight column, which Campus never sends
# --------------------------------------------------------------------------- #

def test_pinned_weight_overrides_the_inference(year9):
    """The sync infers 0.5 for a two-quarter course; the transcript says 0.25."""
    execute("UPDATE courses SET credits = 0.5 WHERE name = 'STEAM Comp Sci'")
    assert gpa.compute()["credits"] == pytest.approx(Y9_WEIGHT + 0.25)
    gpa.set_weight("STEAM Comp Sci", 0.25)
    after = gpa.compute()
    assert after["credits"] == pytest.approx(Y9_WEIGHT)
    row = next(c for c in after["courses"] if c["name"] == "STEAM Comp Sci")
    assert (row["weight"], row["inferred_weight"], row["weight_pinned"]) == (0.25, 0.5, True)


def test_weight_pin_clears(year9):
    gpa.set_weight("Design/Draw - Prod", 3)
    assert gpa.compute()["credits"] == pytest.approx(Y9_WEIGHT + 2)
    assert gpa.set_weight("Design/Draw - Prod", "auto") is None
    assert gpa.compute()["credits"] == pytest.approx(Y9_WEIGHT)


def test_level_and_weight_pins_coexist(year9):
    gpa.set_level("Design/Draw - Prod", "ap")
    gpa.set_weight("Design/Draw - Prod", 0.5)
    row = next(c for c in gpa.compute()["courses"] if c["name"] == "Design/Draw - Prod")
    assert (row["level"], row["weight"]) == ("ap", 0.5)


def test_set_weight_rejects_bad_input(ctx):
    with pytest.raises(ValidationError):
        gpa.set_weight("Biology H", "abc")
    with pytest.raises(ValidationError):
        gpa.set_weight("Biology H", -1)
    with pytest.raises(ValidationError):
        gpa.set_weight("", 1)


def test_weight_api(client, year9):
    r = client.post("/api/gpa/weight", json={"name": "Design/Draw - Prod", "weight": 0.5})
    assert r.status_code == 200
    assert r.get_json()["gpa"]["credits"] == pytest.approx(Y9_WEIGHT - 0.5)
    assert client.post("/api/gpa/weight",
                       json={"name": "X", "weight": "abc"}).status_code == 400


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
    assert r.get_json()["gpa"]["weighted"] == pytest.approx(
        (Y9_MARKS + Y9_BONUS + 5) / Y9_WEIGHT)
    assert client.post("/api/gpa/level", json={"name": "X", "level": "bogus"}).status_code == 400


# --------------------------------------------------------------------------- #
# The four numbers
# --------------------------------------------------------------------------- #

def test_gpa_excludes_courses_campus_excludes(year9):
    result = gpa.compute()
    assert result["count"] == 8
    assert "Phys. Ed. 9" not in {c["name"] for c in result["courses"]}


def test_the_formula_is_sum_of_mark_times_weight(year9):
    result = gpa.compute()
    assert result["credits"] == pytest.approx(Y9_WEIGHT)
    assert result["bonus_points"] == pytest.approx(Y9_BONUS)
    assert result["unweighted"] == pytest.approx(Y9_MARKS / Y9_WEIGHT)
    assert result["weighted"] == pytest.approx((Y9_MARKS + Y9_BONUS) / Y9_WEIGHT)


def test_reproduces_the_official_transcript_exactly(year9):
    """The whole feature in one assertion: grades 8 and 9 must land on the
    transcript's printed 99.1579 / 97.6842."""
    for name, mark, level, weight in GRADE_8:
        gpa.add_manual("2024-2025 Grade 08", name, mark, level, weight)

    result = gpa.compute()
    assert result["credits"] == pytest.approx(9.5)
    assert result["bonus_points"] == pytest.approx(14.0)
    assert round(result["weighted"], 4) == OFFICIAL["weighted"]
    assert round(result["unweighted"], 4) == OFFICIAL["unweighted"]

    for m in gpa.compare(OFFICIAL, result):
        assert m["delta"] == 0, f"{m['model']} is off by {m['delta']}"


def test_zero_weight_course_contributes_nothing(year9):
    """Phys. Ed. is Weight 0.0000 on the transcript. Pinning it to zero must be a
    no-op rather than a division-by-zero or a silent inclusion."""
    before = gpa.compute()["weighted"]
    execute("UPDATE courses SET in_gpa = 1 WHERE name = 'Phys. Ed. 9'")
    gpa.set_weight("Phys. Ed. 9", 0)
    assert gpa.compute()["weighted"] == pytest.approx(before)


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

def test_compare_reports_the_gap_to_the_transcript(year9):
    checked = gpa.compare({"weighted": 99.0, "unweighted": 98.0})
    by_model = {m["model"]: m for m in checked}
    assert by_model["Weighted GPA"]["delta"] == pytest.approx(
        round((Y9_MARKS + Y9_BONUS) / Y9_WEIGHT - 99.0, 4))
    assert by_model["Unweighted GPA"]["official"] == 98.0


def test_compare_without_transcript_figures_still_reports_values(year9):
    checked = gpa.compare(None)
    assert len(checked) == 2
    assert all(m["delta"] is None and m["value"] is not None for m in checked)


def test_official_gpa_round_trips(ctx):
    assert models.official_gpa() == {"weighted": None, "unweighted": None}
    models.set_official_gpa("99.1579", "97.6842")
    assert models.official_gpa() == {"weighted": pytest.approx(99.1579),
                                     "unweighted": pytest.approx(97.6842)}
    models.set_official_gpa(None, None)
    assert models.official_gpa() == {"weighted": None, "unweighted": None}


# --------------------------------------------------------------------------- #
# Hand-entered years: the GPA starts in 8th grade, which Campus will not serve
# --------------------------------------------------------------------------- #

def test_manual_years_join_the_calculation(year9):
    gpa.add_manual("Grade 8", "Algebra 1 H", 95, "honors", 1)
    gpa.add_manual("Grade 8", "Earth Science", 90, "regular", 1)
    result = gpa.compute()
    assert result["count"] == 10
    assert result["credits"] == pytest.approx(Y9_WEIGHT + 2)
    assert result["unweighted"] == pytest.approx((Y9_MARKS + 95 + 90) / (Y9_WEIGHT + 2))
    # The honors bonus applies to the hand-entered course too.
    assert result["weighted"] == pytest.approx(
        (Y9_MARKS + Y9_BONUS + 97 + 90) / (Y9_WEIGHT + 2))
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
    assert [m["model"] for m in body["models"]] == ["Weighted GPA", "Unweighted GPA"]


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
    r = client.post("/api/gpa/official", json={"weighted": 99.1579, "unweighted": 97.6842})
    assert r.status_code == 200
    assert r.get_json()["official"]["weighted"] == pytest.approx(99.1579)
    assert client.post("/api/gpa/official", json={"weighted": "nope"}).status_code == 400


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

def test_grades_page_shows_gpa_and_drops_the_category_tables(client, year9):
    for name, mark, level, weight in GRADE_8:
        gpa.add_manual("2024-2025 Grade 08", name, mark, level, weight)
    models.set_official_gpa(OFFICIAL["weighted"], OFFICIAL["unweighted"])
    html = client.get("/grades").get_data(as_text=True)
    assert "99.1579" in html and "97.6842" in html
    assert html.count("exact") >= 2      # both figures match the transcript
    # "Weakest courses" needs a configured Campus; see test_grades.py.
    assert "Weakest kinds of classwork" not in html
    assert "By course and category" not in html


def test_gpa_renders_without_campus_configured(client, year9):
    """The GPA is computed locally, so it must survive an unreachable portal —
    that is the whole point of the feature."""
    html = client.get("/grades").get_data(as_text=True)
    assert "Connect Infinite Campus" in html      # Campus really is unconfigured
    assert "97.6842" not in html                  # no grade 8 seeded here
    assert f"{Y9_MARKS / Y9_WEIGHT:.4f}" in html  # ...but grade 9 still computes
