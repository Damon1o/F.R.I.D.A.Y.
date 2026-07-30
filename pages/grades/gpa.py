"""GPA, computed locally.

The portal exposes no GPA and no transcript endpoint — every `transcript`, `gpa`
and `reportCard` path 404s — so this never reads a GPA, it derives one. That is
also the point: when the school hides the number, the number is still here.

District rule, quoted from the Bellmore-Merrick Catalog of Courses 2026-2027,
"Student Transcripts":

    Weighted Grades: "Weighted" grades appear on the transcripts of all students.
    Each course grade is "weighted" as follows:
        Advanced Placement Courses              5 points added
        Honors, Accelerated, and Advanced Courses   2 points added

So the bonus applies to the course grade, not to a 4.0-scale point — these are
numeric 0-100 averages. A course counts only if Campus itself marks it
`includedInTermGPA`, which is how Phys. Ed. and lunch drop out; the catalog
publishes no exclusion list of its own.

The catalog publishes no class-rank formula and no credit weighting, which is why
two credit models are reported below. It does publish credits per course as
"(Year Course, 1 Unit)" / "(Semester Course, .5 Unit)", matching the marking-period
inference the sync makes.

Two credit models are reported because the portal does not publish credit hours.
Equal-weight treats every course the same; credit-weighted scales a semester
course to the half-year it actually ran. Compare both against the official number
on a report card — whichever matches is the district's model.
"""
from core.db import execute, query
from pages.calendar.models import ValidationError

BONUS = {"regular": 0.0, "honors": 2.0, "ap": 5.0}
LEVELS = tuple(BONUS)


# The +2 tier, in the catalog's own words. "Advanced" is checked only after
# "Advanced Placement", which is the +5 tier and contains the same word.
BONUS_2_WORDS = ("honors", "accelerated", "advanced")


def detect_level(name: str) -> str:
    """Course level from its name, per the catalog's three weighted categories.

    The catalog spells courses out ("ENGLISH 1 Honors"); Campus abbreviates the
    same course to "English 1 H", so a trailing H counts too — that is how this
    district writes honors in the portal: "Biology H", "Mandarin 2H",
    "English 1H-Fresh Sem".
    """
    n = (name or "").strip()
    low = n.lower()
    padded = f" {low} "
    if "advanced placement" in low or padded.startswith(" ap ") or " ap " in padded:
        return "ap"
    if any(w in low for w in BONUS_2_WORDS):
        return "honors"
    # Split on the punctuation the district uses to glue names together.
    for word in n.replace("-", " ").replace("/", " ").split():
        if len(word) > 1 and word.endswith("H") and word[-2].isdigit():
            return "honors"   # "2H"
        if word == "H":
            return "honors"   # "Biology H"
        if word.endswith("H") and word[:-1].isalpha() and word[:-1].istitle() and len(word) > 3:
            return "honors"   # "BiologyH"
    return "regular"


def level_overrides() -> dict[str, str]:
    """User-pinned levels, keyed by course name. Beat detection and survive sync."""
    return {r["course_name"]: r["level"] for r in
            query("SELECT course_name, level FROM gpa_levels")}


def set_level(course_name: str, level: str) -> str | None:
    """Pin a course's level, or clear the pin with level 'auto'.

    Needed because the catalog weights "Advanced Courses" at +2 and the district
    also offers courses merely *named* Advanced Photography / Advanced Sculpture.
    Guessing either way moves the GPA, so the call is the user's.
    """
    course_name = (course_name or "").strip()
    if not course_name:
        raise ValidationError("course_name is required")
    level = (level or "").strip().lower()
    if level in ("auto", ""):
        execute("DELETE FROM gpa_levels WHERE course_name = %s", (course_name,))
        return None
    if level not in BONUS:
        raise ValidationError(f"level must be auto or one of {', '.join(LEVELS)}")
    execute(
        "INSERT INTO gpa_levels (course_name, level) VALUES (%s, %s) "
        "ON CONFLICT(course_name) DO UPDATE SET level=excluded.level, "
        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
        (course_name, level),
    )
    return level


def _weighted(pct: float, level: str) -> float:
    return pct + BONUS.get(level, 0.0)


def _mean(pairs: list[tuple[float, float]]) -> float | None:
    """Credit-weighted mean of (value, weight). None when there is nothing to average."""
    total_w = sum(w for _v, w in pairs)
    if not total_w:
        return None
    return sum(v * w for v, w in pairs) / total_w


def course_rows() -> list[dict]:
    """Every course that counts toward the GPA: synced current year + hand-entered years."""
    synced = query(
        "SELECT name, final_pct, level, credits, term, 'synced' AS source "
        "FROM courses WHERE in_gpa = 1 AND final_pct IS NOT NULL ORDER BY final_pct DESC"
    )
    manual = query(
        "SELECT id, year, name, final_pct, level, credits, 'manual' AS source "
        "FROM gpa_courses ORDER BY year, name"
    )
    pinned = level_overrides()
    rows = []
    for r in synced:
        detected = r["level"] or detect_level(r["name"])
        rows.append({"id": None, "year": "current", "name": r["name"],
                     "final_pct": r["final_pct"],
                     "level": pinned.get(r["name"], detected),
                     "detected": detected,
                     "pinned": r["name"] in pinned,
                     "credits": r["credits"] or 1.0, "source": "synced"})
    for r in manual:
        rows.append({"id": r["id"], "year": r["year"], "name": r["name"],
                     "final_pct": r["final_pct"], "level": r["level"],
                     "detected": r["level"], "pinned": False,
                     "credits": r["credits"], "source": "manual"})
    return rows


def compute(rows: list[dict] | None = None) -> dict:
    """Both GPA numbers under both credit models, plus the per-course breakdown."""
    rows = course_rows() if rows is None else rows
    for r in rows:
        r["weighted_pct"] = _weighted(r["final_pct"], r["level"])
        r["bonus"] = BONUS.get(r["level"], 0.0)

    equal = [(r, 1.0) for r in rows]
    credited = [(r, r["credits"] or 1.0) for r in rows]

    def by_year() -> list[dict]:
        out = []
        for year in sorted({r["year"] for r in rows}):
            group = [r for r in rows if r["year"] == year]
            out.append({
                "year": year,
                "courses": len(group),
                "credits": round(sum(r["credits"] or 1.0 for r in group), 2),
                "unweighted": _mean([(r["final_pct"], 1.0) for r in group]),
                "weighted": _mean([(r["weighted_pct"], 1.0) for r in group]),
            })
        return out

    return {
        "courses": rows,
        "count": len(rows),
        "credits": round(sum(r["credits"] or 1.0 for r in rows), 2),
        "unweighted": _mean([(r["final_pct"], w) for r, w in equal]),
        "weighted": _mean([(r["weighted_pct"], w) for r, w in equal]),
        "unweighted_credited": _mean([(r["final_pct"], w) for r, w in credited]),
        "weighted_credited": _mean([(r["weighted_pct"], w) for r, w in credited]),
        "years": by_year(),
        "honors": sum(1 for r in rows if r["level"] == "honors"),
        "ap": sum(1 for r in rows if r["level"] == "ap"),
    }


def compare(official: float | None, result: dict | None = None) -> list[dict]:
    """Rank the four models by how close they land to the official GPA.

    This is the accuracy check: the model with the smallest delta is the one the
    district uses, and a delta of zero means the local calculation is exact.
    """
    result = compute() if result is None else result
    models = [
        ("Weighted, equal credit", result["weighted"]),
        ("Weighted, credit-scaled", result["weighted_credited"]),
        ("Unweighted, equal credit", result["unweighted"]),
        ("Unweighted, credit-scaled", result["unweighted_credited"]),
    ]
    out = [{"model": label, "value": val,
            "delta": None if (official is None or val is None) else round(val - official, 3)}
           for label, val in models]
    out.sort(key=lambda m: (m["delta"] is None, abs(m["delta"] or 0)))
    return out


# --------------------------------------------------------------------------- #
# Hand-entered years (8th grade and anything else the portal can't reach)
# --------------------------------------------------------------------------- #

def add_manual(year: str, name: str, final_pct, level: str = "regular", credits=1.0) -> dict:
    year = (year or "").strip()
    name = (name or "").strip()
    if not year or not name:
        raise ValidationError("year and name are required")
    try:
        final_pct = float(final_pct)
    except (TypeError, ValueError):
        raise ValidationError("final_pct must be a number")
    if not 0 <= final_pct <= 150:  # 150 leaves room for a weighted mark pasted by mistake
        raise ValidationError("final_pct must be between 0 and 150")
    level = (level or "regular").strip().lower()
    if level not in BONUS:
        raise ValidationError(f"level must be one of {', '.join(LEVELS)}")
    try:
        credits = float(credits)
    except (TypeError, ValueError):
        raise ValidationError("credits must be a number")
    if credits <= 0:
        raise ValidationError("credits must be positive")
    row = execute(
        "INSERT INTO gpa_courses (year, name, final_pct, level, credits) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (year, name, final_pct, level, credits),
    ).fetchone()
    return {"id": row["id"], "year": year, "name": name, "final_pct": final_pct,
            "level": level, "credits": credits}


def delete_manual(row_id: int) -> bool:
    return execute("DELETE FROM gpa_courses WHERE id = %s", (row_id,)).rowcount > 0
