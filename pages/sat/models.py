"""SAT Prep: three question-writing agents, grading, and a weak-skill ranking.

The "agents" are three system prompts — Math, Reading, Writing — each pinned to
the College Board taxonomy for its half of the test. One DeepSeek call per set;
the answer key never leaves the server, so grading happens in `answer()`.
"""
import json
import re

from core.db import execute, query

# --------------------------------------------------------------------------- #
# College Board taxonomy (SAT Suite Question Bank): section -> domain -> skills.
# Reading and Writing is one scored section on test day; it is split in two here
# because the two halves need different question writers.
# --------------------------------------------------------------------------- #
TAXONOMY = {
    "reading": {
        "Information and Ideas": ["Central Ideas and Details", "Inferences",
                                  "Command of Evidence"],
        "Craft and Structure": ["Words in Context", "Text Structure and Purpose",
                                "Cross-Text Connections"],
    },
    "writing": {
        "Expression of Ideas": ["Rhetorical Synthesis", "Transitions"],
        "Standard English Conventions": ["Boundaries", "Form, Structure, and Sense"],
    },
    "math": {
        "Algebra": ["Linear equations in one variable", "Linear functions",
                    "Systems of two linear equations", "Linear inequalities"],
        "Advanced Math": ["Equivalent expressions", "Nonlinear equations",
                          "Nonlinear functions"],
        "Problem-Solving and Data Analysis": ["Ratios, rates, and proportions",
                                              "Percentages", "One-variable data",
                                              "Probability", "Inference from samples"],
        "Geometry and Trigonometry": ["Area and volume", "Lines, angles, and triangles",
                                      "Right triangles and trigonometry", "Circles"],
    },
}

SECTIONS = list(TAXONOMY)
DIFFICULTIES = ("easy", "medium", "hard")

_STYLE = {
    "reading": (
        "You write SAT Reading questions. Each one is a self-contained passage of "
        "25-150 words (literature, science, history, or a social-studies excerpt; "
        "for Command of Evidence you may use a short data description) followed by "
        "one question and four choices. Exactly one choice is defensible from the "
        "text alone. Distractors must be wrong for a real reason: half-right scope, "
        "a true statement the passage never makes, or a reversed relationship."
    ),
    "writing": (
        "You write SAT Writing and Language questions. Give a short passage or "
        "sentence, then one question with four choices. Conventions items test "
        "punctuation, boundaries, agreement, and modifier placement — the choices "
        "differ only in the mechanics under test. Rhetorical Synthesis items give "
        "3-5 bulleted notes and a stated goal."
    ),
    "math": (
        "You write SAT Math questions. Calculator-neutral, solvable in about 90 "
        "seconds, no calculus and no proofs. Use plain text math (x^2, sqrt(5), "
        "3/4) — no LaTeX, no images, no unicode symbols. Every distractor is the "
        "result of a specific plausible error (sign flip, wrong operation order, "
        "solving for the wrong variable), never a random number."
    ),
}

_FORMAT = (
    'Return ONLY a JSON array, no prose and no code fence. Each element: '
    '{"stimulus": string ("" when the question needs no passage), '
    '"prompt": string, "choices": [4 strings, no "A)" labels], '
    '"answer": "A"|"B"|"C"|"D", "explanation": string (max 2 sentences)}. '
    'Vary which letter is correct. Never reuse a passage or a number from a '
    'question you were shown as already asked.'
)


def prompt_for(section: str, skill: str, difficulty: str) -> str:
    return (f"{_STYLE[section]}\n\nWrite questions for the skill: {skill} "
            f"({domain_of(section, skill)}), difficulty: {difficulty}.\n\n{_FORMAT}")


def domain_of(section: str, skill: str) -> str:
    for domain, skills in TAXONOMY[section].items():
        if skill in skills:
            return domain
    raise ValueError(f"unknown skill for {section}: {skill}")


def skills(section: str) -> list[str]:
    return [s for skills_ in TAXONOMY[section].values() for s in skills_]


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def _parse(text: str) -> list[dict]:
    """The model is told to return bare JSON; it sometimes fences it anyway."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    if isinstance(data, dict):                 # a lone object, or {"questions": [...]}
        data = data.get("questions", [data])
    return [q for q in data if isinstance(q, dict)]


def _clean(q: dict) -> dict | None:
    """Drop anything that would render as a broken question."""
    choices = q.get("choices")
    answer = str(q.get("answer", "")).strip().upper()[:1]
    if not isinstance(choices, list) or len(choices) != 4 or answer not in "ABCD":
        return None
    if not str(q.get("prompt", "")).strip():
        return None
    return {"stimulus": str(q.get("stimulus") or "").strip(),
            "prompt": str(q["prompt"]).strip(),
            "choices": [str(c).strip() for c in choices],
            "answer": answer,
            "explanation": str(q.get("explanation") or "").strip()}


def _seen(section: str, skill: str) -> str:
    """Prompts already written for this skill — fed back so the writer varies."""
    rows = query("SELECT prompt FROM sat_questions WHERE section = %s AND skill = %s"
                 " ORDER BY id DESC LIMIT 12", (section, skill))
    if not rows:
        return ""
    return "\n\nAlready asked (do not repeat):\n" + "\n".join(f"- {r['prompt']}" for r in rows)


def _ask(client, section: str, skill: str, difficulty: str, count: int,
         seen: str = "") -> list[dict]:
    """One LLM call. No database access — safe to run in a worker thread."""
    msg = client.complete([
        {"role": "system", "content": prompt_for(section, skill, difficulty)},
        {"role": "user", "content": f"Write {count} questions.{seen}"},
    ])
    cleaned = (_clean(item) for item in _parse(msg.get("content") or "")[:count])
    return [q for q in cleaned if q]


_VERIFY_PROMPT = (
    "You are an SAT answer-key checker. Solve each numbered question yourself from "
    "scratch. Ignore any key you are shown — you are not given one. Return ONLY a "
    'JSON array of objects: {"n": number, "answer": "A"|"B"|"C"|"D"}. One entry per '
    "question, in order, no prose and no code fence."
)


def _verifier(client=None):
    """A *different* model, solving independently. Same account, same base URL."""
    from core.llm import DeepSeekClient
    from flask import current_app

    if client is not None:
        return client
    return DeepSeekClient(model=current_app.config["DEEPSEEK_VERIFY_MODEL"])


def verify(questions: list[dict], client=None) -> list[dict]:
    """Keep only the questions whose key a second model independently agrees with.

    The writer model does get its own key wrong — it will explain its way to 63 pi
    and then mark 147 pi correct. A wrong key is worse than a missing question, so
    a disagreement drops the question. HTTP only, no database: thread-safe.
    """
    from core.llm import LLMError

    if not questions:
        return []
    listing = "\n\n".join(
        f"{i + 1}. {q['stimulus']}\n{q['prompt']}\n" +
        "\n".join(f"{'ABCD'[j]}. {c}" for j, c in enumerate(q["choices"]))
        for i, q in enumerate(questions))
    try:
        msg = _verifier(client).complete([
            {"role": "system", "content": _VERIFY_PROMPT},
            {"role": "user", "content": listing},
        ])
        votes = {int(v["n"]): str(v.get("answer", "")).strip().upper()[:1]
                 for v in _parse(msg.get("content") or "") if str(v.get("n", "")).isdigit()}
    except (LLMError, ValueError, KeyError, TypeError):
        return questions        # checker unreachable: ship the set rather than nothing
    return [q for i, q in enumerate(questions) if votes.get(i + 1, q["answer"]) == q["answer"]]


def _store(section: str, skill: str, difficulty: str, q: dict) -> dict:
    """Insert one question; return it without the answer key."""
    row = execute(
        "INSERT INTO sat_questions (section, domain, skill, difficulty, stimulus,"
        " prompt, choices, answer, explanation)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (section, domain_of(section, skill), skill, difficulty, q["stimulus"], q["prompt"],
         json.dumps(q["choices"]), q["answer"], q["explanation"]),
    ).fetchone()
    return {"id": row["id"], "section": section, "domain": domain_of(section, skill),
            "skill": skill, "difficulty": difficulty, "stimulus": q["stimulus"],
            "prompt": q["prompt"], "choices": q["choices"]}


def generate(section: str, skill: str | None = None, difficulty: str = "medium",
             count: int = 4, client=None, checker=None) -> dict:
    """Write `count` fresh questions for one skill and store them."""
    from core.llm import DeepSeekClient, LLMError

    if section not in TAXONOMY:
        return {"error": f"Unknown section: {section}", "questions": []}
    skill = skill or weakest_skill(section)
    if skill not in skills(section):
        return {"error": f"Unknown skill: {skill}", "questions": []}
    if difficulty not in DIFFICULTIES:
        difficulty = "medium"
    count = max(1, min(int(count or 4), 8))

    client = client or DeepSeekClient()
    if not getattr(client, "api_key", ""):
        return {"error": "SAT practice needs an LLM API key.", "questions": []}

    try:
        written = _ask(client, section, skill, difficulty, count, _seen(section, skill))
        written = verify(written, checker or _verifier())
    except LLMError as e:
        return {"error": str(e), "questions": []}
    except ValueError:
        return {"error": "F.R.I.D.A.Y. returned an unreadable question set.",
                "questions": []}

    out = [_store(section, skill, difficulty, q) for q in written]
    if not out:
        return {"error": "Every question failed the answer-key check. Try again.",
                "questions": []}
    return {"error": None, "skill": skill, "domain": domain_of(section, skill),
            "difficulty": difficulty, "questions": out}


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #
def answer(question_id, chosen: str) -> dict:
    chosen = str(chosen or "").strip().upper()[:1]
    if chosen not in "ABCD" or not chosen:
        return {"error": "Pick a choice."}
    q = query("SELECT * FROM sat_questions WHERE id = %s", (question_id,), one=True)
    if not q:
        return {"error": "No such question."}
    correct = int(chosen == q["answer"])
    execute("INSERT INTO sat_attempts (question_id, chosen, correct) VALUES (%s, %s, %s)",
            (question_id, chosen, correct))
    return {"error": None, "correct": bool(correct), "answer": q["answer"],
            "explanation": q["explanation"], "skill": q["skill"]}


# --------------------------------------------------------------------------- #
# Progress — SQL only, no LLM
# --------------------------------------------------------------------------- #
def progress() -> dict:
    """Per-skill accuracy, worst first, plus section and overall totals."""
    rows = query(
        "SELECT q.section, q.domain, q.skill, COUNT(*) AS asked,"
        " SUM(a.correct) AS right_count"
        " FROM sat_attempts a JOIN sat_questions q ON q.id = a.question_id"
        " GROUP BY q.section, q.domain, q.skill")
    by_skill = []
    for r in rows:
        asked = r["asked"]
        by_skill.append({**r, "right_count": r["right_count"] or 0,
                         "accuracy": round(100.0 * (r["right_count"] or 0) / asked, 1)})
    by_skill.sort(key=lambda s: (s["accuracy"], -s["asked"]))

    sections = {}
    for s in by_skill:
        acc = sections.setdefault(s["section"], {"asked": 0, "right_count": 0})
        acc["asked"] += s["asked"]
        acc["right_count"] += s["right_count"]
    for name, acc in sections.items():
        acc["accuracy"] = round(100.0 * acc["right_count"] / acc["asked"], 1)

    asked = sum(s["asked"] for s in by_skill)
    return {"skills": by_skill, "sections": sections, "asked": asked,
            "right_count": sum(s["right_count"] for s in by_skill),
            "accuracy": round(100.0 * sum(s["right_count"] for s in by_skill) / asked, 1)
            if asked else None,
            "untouched": {sec: [s for s in skills(sec)
                                if not any(r["skill"] == s and r["section"] == sec
                                           for r in by_skill)]
                          for sec in SECTIONS}}


def reset() -> dict:
    """Wipe attempts and tests. The question bank survives — those questions go
    back to being unused, so the next test reuses them instead of paying to
    rewrite them."""
    tests = execute("DELETE FROM sat_tests").rowcount        # items cascade
    attempts = execute("DELETE FROM sat_attempts").rowcount
    return {"attempts": attempts, "tests": tests}


def weakest_skill(section: str) -> str:
    """What to drill next: an unpracticed skill first, else the lowest accuracy."""
    data = progress()
    untouched = data["untouched"][section]
    if untouched:
        return untouched[0]
    ranked = [s for s in data["skills"] if s["section"] == section]
    return ranked[0]["skill"] if ranked else skills(section)[0]


# --------------------------------------------------------------------------- #
# Full-length test
#
# Official digital SAT shape: two Reading and Writing modules (27 questions /
# 32 min each) then two Math modules (22 / 35). Module 2 is adaptive — the real
# test routes you to a harder or easier second module on your module 1 score, so
# that is when it gets written, not before.
# --------------------------------------------------------------------------- #
MODULES = {
    "rw1":   {"parts": ("reading", "writing"), "count": 27, "minutes": 32,
              "label": "Reading and Writing · Module 1"},
    "rw2":   {"parts": ("reading", "writing"), "count": 27, "minutes": 32,
              "label": "Reading and Writing · Module 2"},
    "math1": {"parts": ("math",), "count": 22, "minutes": 35, "label": "Math · Module 1"},
    "math2": {"parts": ("math",), "count": 22, "minutes": 35, "label": "Math · Module 2"},
}
MODULE_ORDER = ("rw1", "rw2", "math1", "math2")


def _plan(module: str) -> list[tuple[str, str]]:
    """(section, skill) for every seat in the module.

    ponytail: round-robin over the skills instead of the College Board's
    percentage weighting — every skill gets covered, and the weighting only
    shifts a question or two per domain at these counts.
    """
    pool = [(sec, skill) for sec in MODULES[module]["parts"] for skill in skills(sec)]
    return [pool[i % len(pool)] for i in range(MODULES[module]["count"])]


def _bank(section: str, skill: str, difficulty: str, limit: int) -> list[dict]:
    """Written-but-never-served questions. Reuse is what keeps a re-test cheap."""
    if limit <= 0:
        return []
    return query(
        "SELECT id, section, domain, skill, difficulty, stimulus, prompt, choices"
        " FROM sat_questions q WHERE q.section = %s AND q.skill = %s AND q.difficulty = %s"
        " AND NOT EXISTS (SELECT 1 FROM sat_attempts a WHERE a.question_id = q.id)"
        " AND NOT EXISTS (SELECT 1 FROM sat_test_items t WHERE t.question_id = q.id)"
        " ORDER BY q.id LIMIT %s", (section, skill, difficulty, limit))


def _difficulty_for(test_id, module: str) -> str:
    """Module 1 is mixed-medium; module 2 is the adaptive one."""
    if module in ("rw1", "math1"):
        return "medium"
    first = "rw1" if module == "rw2" else "math1"
    row = query("SELECT COUNT(*) AS asked, COALESCE(SUM(correct), 0) AS right_count"
                " FROM sat_test_items WHERE test_id = %s AND module = %s AND chosen IS NOT NULL",
                (test_id, first), one=True)
    if not row or not row["asked"]:
        return "medium"
    return "hard" if row["right_count"] / row["asked"] >= 0.6 else "easy"


def build_module(test_id, module: str, client=None, checker=None) -> dict:
    """Fill one module: bank first, then one LLM call per skill still short."""
    from concurrent.futures import ThreadPoolExecutor

    from core.llm import DeepSeekClient, LLMError

    if module not in MODULES:
        return {"error": f"Unknown module: {module}"}
    if query("SELECT id FROM sat_test_items WHERE test_id = %s AND module = %s LIMIT 1",
             (test_id, module), one=True):
        return {"error": None, **serve_module(test_id, module)}

    difficulty = _difficulty_for(test_id, module)
    need: dict[tuple[str, str], int] = {}
    for seat in _plan(module):
        need[seat] = need.get(seat, 0) + 1

    # Everything touching the database happens out here; the threads only do HTTP.
    pooled, shortfall = {}, []
    for (section, skill), n in need.items():
        rows = _bank(section, skill, difficulty, n)
        pooled[(section, skill)] = [dict(r, choices=json.loads(r["choices"])) for r in rows]
        if len(rows) < n:
            # One spare per bucket: the answer-key check throws some away, and a
            # module short of its 27 seats is worse than one extra question written.
            shortfall.append((section, skill, n - len(rows) + 1, _seen(section, skill)))

    if shortfall:
        client = client or DeepSeekClient()
        if not getattr(client, "api_key", ""):
            return {"error": "A full test needs an LLM API key."}
        # Both clients are built out here: a worker thread has no app context, so
        # it cannot read config to make one.
        checker = checker or _verifier()

        def write(job):
            section, skill, n, seen = job
            try:
                return job, verify(_ask(client, section, skill, difficulty, n, seen), checker)
            except (LLMError, ValueError):
                return job, []          # short a few questions beats no test

        # One worker per skill: every bucket is a write plus a slower second-model
        # check, so running them in one wave is what keeps a module near a minute.
        with ThreadPoolExecutor(max_workers=max(1, len(shortfall))) as pool:
            for (section, skill, _n, _s), written in pool.map(write, shortfall):
                pooled[(section, skill)] += [_store(section, skill, difficulty, q)
                                             for q in written]

    position = 0
    for seat in _plan(module):
        bucket = pooled.get(seat)
        if not bucket:
            continue                     # that skill came back empty; skip the seat
        q = bucket.pop(0)
        position += 1
        execute("INSERT INTO sat_test_items (test_id, module, position, question_id)"
                " VALUES (%s, %s, %s, %s)", (test_id, module, position, q["id"]))
    if not position:
        return {"error": "Could not write this module. Try again."}
    return {"error": None, **serve_module(test_id, module)}


def serve_module(test_id, module: str) -> dict:
    """The module as the test taker sees it: questions, no answer key."""
    rows = query(
        "SELECT i.id AS item_id, i.position, i.chosen, q.stimulus, q.prompt, q.choices,"
        " q.skill, q.section FROM sat_test_items i JOIN sat_questions q ON q.id = i.question_id"
        " WHERE i.test_id = %s AND i.module = %s ORDER BY i.position", (test_id, module))
    return {"test_id": test_id, "module": module, "label": MODULES[module]["label"],
            "minutes": MODULES[module]["minutes"],
            "questions": [dict(r, choices=json.loads(r["choices"])) for r in rows]}


def start_test(client=None, checker=None) -> dict:
    row = execute("INSERT INTO sat_tests DEFAULT VALUES RETURNING id").fetchone()
    built = build_module(row["id"], "rw1", client=client, checker=checker)
    if built["error"]:
        execute("DELETE FROM sat_tests WHERE id = %s", (row["id"],))
    return built


def answer_item(item_id, chosen: str) -> dict:
    """Record one test answer. Also counted in the skill ranking."""
    chosen = str(chosen or "").strip().upper()[:1]
    if chosen not in "ABCD" or not chosen:
        return {"error": "Pick a choice."}
    item = query("SELECT i.*, q.answer FROM sat_test_items i"
                 " JOIN sat_questions q ON q.id = i.question_id WHERE i.id = %s",
                 (item_id,), one=True)
    if not item:
        return {"error": "No such question."}
    if item["chosen"]:
        return {"error": None, "already": True, "correct": bool(item["correct"]),
                "remaining": 0, "next_module": None}
    correct = int(chosen == item["answer"])
    execute("UPDATE sat_test_items SET chosen = %s, correct = %s WHERE id = %s",
            (chosen, correct, item_id))
    execute("INSERT INTO sat_attempts (question_id, chosen, correct) VALUES (%s, %s, %s)",
            (item["question_id"], chosen, correct))
    remaining = query("SELECT COUNT(*) AS n FROM sat_test_items"
                      " WHERE test_id = %s AND module = %s AND chosen IS NULL",
                      (item["test_id"], item["module"]), one=True)["n"]
    nxt = None
    if not remaining and item["module"] != MODULE_ORDER[-1]:
        nxt = MODULE_ORDER[MODULE_ORDER.index(item["module"]) + 1]
    return {"error": None, "correct": bool(correct), "remaining": remaining,
            "next_module": nxt}


def _scale(correct: int, asked: int, hard_track: bool) -> int:
    """Raw accuracy to a 200-800 section score.

    ponytail: the real conversion is a per-form equating table College Board does
    not publish. This is a straight line with the adaptive routing applied — the
    easy module 2 caps out near where the real one does.
    """
    if not asked:
        return 200
    score_ = 200 + 600 * (correct / asked)
    score_ = max(score_, 400) if hard_track else min(score_, 600)
    return int(round(min(800, max(200, score_)) / 10) * 10)


TARGET = 1530     # the score to beat; every chart is drawn against this line


def score(test_id) -> dict:
    rows = query("SELECT module, COUNT(*) AS asked, COALESCE(SUM(correct), 0) AS right_count"
                 " FROM sat_test_items WHERE test_id = %s AND chosen IS NOT NULL"
                 " GROUP BY module", (test_id,))
    by_module = {r["module"]: r for r in rows}
    out = {}
    for section, (first, second) in (("rw", ("rw1", "rw2")), ("math", ("math1", "math2"))):
        asked = sum(by_module.get(m, {}).get("asked", 0) for m in (first, second))
        right = sum(by_module.get(m, {}).get("right_count", 0) for m in (first, second))
        m1 = by_module.get(first)
        hard = bool(m1 and m1["asked"] and m1["right_count"] / m1["asked"] >= 0.6)
        out[section] = {"asked": asked, "right_count": right,
                        "score": _scale(right, asked, hard), "hard_track": hard}
    out["total"] = out["rw"]["score"] + out["math"]["score"]
    out["target"] = TARGET
    out["gap"] = max(0, TARGET - out["total"])
    return out


def finish_test(test_id) -> dict:
    result = score(test_id)
    execute("UPDATE sat_tests SET finished_at = to_char(now() at time zone 'utc',"
            " 'YYYY-MM-DD HH24:MI:SS'), rw_score = %s, math_score = %s WHERE id = %s",
            (result["rw"]["score"], result["math"]["score"], test_id))
    return result


def tests(limit: int = 5) -> list[dict]:
    """Finished tests, newest first — the score history on the page."""
    return query("SELECT id, started_at, finished_at, rw_score, math_score,"
                 " rw_score + math_score AS total FROM sat_tests"
                 " WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT %s", (limit,))


def chart(limit: int = 8) -> dict | None:
    """Score history as SVG geometry, oldest first, drawn against the target.

    ponytail: the geometry is computed here and the template just prints it —
    an inline <svg> beats shipping a charting library for one 300x120 line.
    """
    rows = list(reversed(tests(limit)))
    if not rows:
        return None
    w, h, lo, hi = 300.0, 120.0, 400, 1600      # 400-1600 is the range a total can land in

    def y(value):
        return round(h - (min(hi, max(lo, value)) - lo) / (hi - lo) * h, 1)

    step = w / (len(rows) - 1) if len(rows) > 1 else 0
    points = [{"x": round(i * step, 1) if len(rows) > 1 else w / 2, "y": y(r["total"]),
               "total": r["total"], "date": (r["finished_at"] or "")[:10]}
              for i, r in enumerate(rows)]
    line = " ".join(f"{p['x']},{p['y']}" for p in points)
    latest = rows[-1]["total"]
    return {"points": points, "line": line, "w": w, "h": h,
            "area": f"{points[0]['x']},{h} {line} {points[-1]['x']},{h}",
            "target": TARGET, "target_y": y(TARGET), "latest": latest,
            "gap": max(0, TARGET - latest),
            "best": max(r["total"] for r in rows)}


def open_test() -> dict | None:
    """The test still in progress, if there is one, plus where it left off."""
    row = query("SELECT id FROM sat_tests WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1",
                one=True)
    if not row:
        return None
    counts = {r["module"]: r for r in query(
        "SELECT module, COUNT(*) AS total, COUNT(chosen) AS answered"
        " FROM sat_test_items WHERE test_id = %s GROUP BY module", (row["id"],))}
    for module in MODULE_ORDER:
        state = counts.get(module)
        if state is None or state["answered"] < state["total"]:
            return {"test_id": row["id"], "module": module, "started": state is not None}
    return {"test_id": row["id"], "module": None, "started": True}   # all four answered
