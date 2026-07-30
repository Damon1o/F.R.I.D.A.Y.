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

The catalog does not publish the combining formula, but an official Mepham
transcript pins it exactly. Every course carries a Weight, and:

    unweighted = SUM(mark * weight) / SUM(weight)
    weighted   = SUM((mark + bonus) * weight) / SUM(weight)

Verified against the transcript generated 2026-07-29: SUM(weight) 9.5 over grades
8 and 9, SUM(mark * weight) 928 -> 97.6842, plus 14 points of bonus -> 99.1579.
Both reproduce the printed figures to four decimals.

Weight is not credit. Phys. Ed. prints 0.500 credit against Weight 0.0000: it
earns credit and no GPA. Campus publishes neither number, so weight is inferred
from the share of marking periods a course ran and can be pinned per course — the
transcript prints STEAM Comp Sci at 0.25 where that inference says 0.5.
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


def overrides() -> dict[str, dict]:
    """User pins, keyed by course name. Beat detection and survive a resync."""
    return {r["course_name"]: {"level": r["level"], "weight": r["weight"]}
            for r in query("SELECT course_name, level, weight FROM gpa_levels")}


def _pin(course_name: str, column: str, value) -> None:
    execute(
        f"INSERT INTO gpa_levels (course_name, {column}) VALUES (%s, %s) "
        f"ON CONFLICT(course_name) DO UPDATE SET {column}=excluded.{column}, "
        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
        (course_name, value),
    )
    # A row pinning nothing is just clutter.
    execute("DELETE FROM gpa_levels WHERE course_name = %s "
            "AND level IS NULL AND weight IS NULL", (course_name,))


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
        _pin(course_name, "level", None)
        return None
    if level not in BONUS:
        raise ValidationError(f"level must be auto or one of {', '.join(LEVELS)}")
    _pin(course_name, "level", level)
    return level


def set_weight(course_name: str, weight) -> float | None:
    """Pin a course's GPA weight, or clear it with '' / 'auto'.

    The transcript's Weight column is authoritative and Campus never sends it.
    Zero is a legal pin: that is exactly how Phys. Ed. is carried.
    """
    course_name = (course_name or "").strip()
    if not course_name:
        raise ValidationError("course_name is required")
    if weight in (None, "", "auto"):
        _pin(course_name, "weight", None)
        return None
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        raise ValidationError("weight must be a number")
    if weight < 0:
        raise ValidationError("weight cannot be negative")
    _pin(course_name, "weight", weight)
    return weight


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
    pinned = overrides()
    rows = []
    for r in synced:
        pin = pinned.get(r["name"], {})
        detected = r["level"] or detect_level(r["name"])
        inferred = r["credits"] if r["credits"] is not None else 1.0
        rows.append({"id": None, "year": "current", "name": r["name"],
                     "final_pct": r["final_pct"],
                     "level": pin.get("level") or detected,
                     "detected": detected,
                     "level_pinned": pin.get("level") is not None,
                     "weight": pin["weight"] if pin.get("weight") is not None else inferred,
                     "inferred_weight": inferred,
                     "weight_pinned": pin.get("weight") is not None,
                     "source": "synced"})
    for r in manual:
        rows.append({"id": r["id"], "year": r["year"], "name": r["name"],
                     "final_pct": r["final_pct"], "level": r["level"],
                     "detected": r["level"], "level_pinned": False,
                     "weight": r["credits"], "inferred_weight": r["credits"],
                     "weight_pinned": False, "source": "manual"})
    return rows


def _totals(rows: list[dict]) -> dict:
    """The district formula: SUM(mark * weight) / SUM(weight), bonus inside."""
    return {
        "weight": round(sum(r["weight"] for r in rows), 4),
        "unweighted": _mean([(r["final_pct"], r["weight"]) for r in rows]),
        "weighted": _mean([(r["weighted_pct"], r["weight"]) for r in rows]),
    }


def compute(rows: list[dict] | None = None) -> dict:
    """The GPA, plus the per-course breakdown that produced it."""
    rows = course_rows() if rows is None else rows
    for r in rows:
        r["weighted_pct"] = _weighted(r["final_pct"], r["level"])
        r["bonus"] = BONUS.get(r["level"], 0.0)

    years = [dict(year=year, courses=len(group),
                  **_totals(group))
             for year in sorted({r["year"] for r in rows})
             for group in [[r for r in rows if r["year"] == year]]]

    return {
        "courses": rows,
        "count": len(rows),
        "credits": round(sum(r["weight"] for r in rows), 4),
        "bonus_points": round(sum(r["bonus"] * r["weight"] for r in rows), 4),
        "years": years,
        "honors": sum(1 for r in rows if r["level"] == "honors"),
        "ap": sum(1 for r in rows if r["level"] == "ap"),
        **_totals(rows),
    }


def compare(official: dict | None = None, result: dict | None = None) -> list[dict]:
    """Computed against the transcript's own figures. Delta zero means exact."""
    result = compute() if result is None else result
    official = official or {}
    out = []
    for key, label in (("weighted", "Weighted GPA"), ("unweighted", "Unweighted GPA")):
        value, want = result[key], official.get(key)
        out.append({
            "model": label,
            "value": value,
            "official": want,
            # Four decimals: the transcript prints 99.1579, and a match has to be
            # a match at that precision to mean anything.
            "delta": None if (want is None or value is None) else round(value - want, 4),
        })
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
