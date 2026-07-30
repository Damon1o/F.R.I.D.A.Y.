"""GPA, computed locally.

The portal exposes no GPA and no transcript endpoint — every `transcript`, `gpa`
and `reportCard` path 404s — so this never reads a GPA, it derives one. That is
also the point: when the school hides the number, the number is still here.

District rules, as given: grades are numeric 0-100 averages, Honors adds 2 points
to a course average and AP adds 5. A course counts only if Campus itself marks it
`includedInTermGPA`, which is how Phys. Ed. and lunch drop out.

Two credit models are reported because the portal does not publish credit hours.
Equal-weight treats every course the same; credit-weighted scales a semester
course to the half-year it actually ran. Compare both against the official number
on a report card — whichever matches is the district's model.
"""
from core.db import execute, query
from pages.calendar.models import ValidationError

BONUS = {"regular": 0.0, "honors": 2.0, "ap": 5.0}
LEVELS = tuple(BONUS)


def detect_level(name: str) -> str:
    """Course level from its name. 'AP Biology' -> ap, 'Mandarin 2H' -> honors.

    Honors is marked by a trailing H on the name or on one of its words, which is
    how this district writes it: "Biology H", "Mandarin 2H", "English 1H-Fresh Sem".
    """
    n = (name or "").strip()
    low = n.lower()
    if low.startswith("ap ") or " ap " in f" {low} " or low.startswith("advanced placement"):
        return "ap"
    if "honors" in low:
        return "honors"
    # Split on spaces and punctuation the district uses to glue names together.
    for word in n.replace("-", " ").replace("/", " ").split():
        if len(word) > 1 and word.endswith("H") and word[-2].isdigit():
            return "honors"   # "2H"
        if word == "H":
            return "honors"   # "Biology H"
        if word.endswith("H") and word[:-1].isalpha() and word[:-1].istitle() and len(word) > 3:
            return "honors"   # "BiologyH"
    return "regular"


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
    rows = []
    for r in synced:
        rows.append({"id": None, "year": "current", "name": r["name"],
                     "final_pct": r["final_pct"],
                     "level": r["level"] or detect_level(r["name"]),
                     "credits": r["credits"] or 1.0, "source": "synced"})
    for r in manual:
        rows.append({"id": r["id"], "year": r["year"], "name": r["name"],
                     "final_pct": r["final_pct"], "level": r["level"],
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
