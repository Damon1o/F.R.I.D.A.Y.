"""SAT Prep: generation parsing/storage, grading, and the weak-skill ranking. No network."""
import json

from core.db import execute, query
from pages.sat import models


class FakeLLM:
    """Stands in for DeepSeekClient: returns canned content, records the prompt."""

    api_key = "test"

    def __init__(self, content):
        self.content = content
        self.messages = None

    def complete(self, messages, tools=None):
        self.messages = messages
        return {"role": "assistant", "content": self.content}


def _payload(n=2, answer="B"):
    return json.dumps([
        {"stimulus": f"Passage {i}", "prompt": f"Question {i}?",
         "choices": ["one", "two", "three", "four"], "answer": answer,
         "explanation": "Because."}
        for i in range(n)
    ])


AGREE = "[]"          # no votes cast: verify() keeps whatever the writer said


def _votes(*letters):
    return json.dumps([{"n": i + 1, "answer": a} for i, a in enumerate(letters)])


def test_taxonomy_skills_map_to_a_domain():
    for section in models.SECTIONS:
        for skill in models.skills(section):
            assert models.domain_of(section, skill) in models.TAXONOMY[section]


def test_generate_stores_questions_without_leaking_the_key(ctx):
    result = models.generate("math", "Percentages", "hard", 2, client=FakeLLM(_payload()))
    assert result["error"] is None
    assert len(result["questions"]) == 2
    assert "answer" not in result["questions"][0]
    row = query("SELECT * FROM sat_questions WHERE id = %s",
                (result["questions"][0]["id"],), one=True)
    assert row["domain"] == "Problem-Solving and Data Analysis"
    assert row["difficulty"] == "hard"
    assert json.loads(row["choices"]) == ["one", "two", "three", "four"]


def test_generate_tolerates_a_code_fence_and_drops_broken_items(ctx):
    fenced = "```json\n" + json.dumps([
        {"prompt": "Good?", "choices": ["a", "b", "c", "d"], "answer": "C"},
        {"prompt": "Too few choices?", "choices": ["a", "b"], "answer": "A"},
        {"prompt": "Bad letter?", "choices": ["a", "b", "c", "d"], "answer": "E"},
    ]) + "\n```"
    result = models.generate("writing", "Transitions", count=4, client=FakeLLM(fenced))
    assert [q["prompt"] for q in result["questions"]] == ["Good?"]


def test_generate_rejects_unusable_output(ctx):
    assert models.generate("math", "Percentages", client=FakeLLM("not json"))["error"]
    assert models.generate("nope", "Percentages", client=FakeLLM(_payload()))["error"]
    assert models.generate("math", "Nonexistent skill", client=FakeLLM(_payload()))["error"]


def test_generate_needs_an_api_key(ctx):
    class NoKey(FakeLLM):
        api_key = ""

    assert "API key" in models.generate("math", "Percentages", client=NoKey(""))["error"]


def test_generate_feeds_back_prompts_already_asked(ctx):
    models.generate("math", "Percentages", count=2, client=FakeLLM(_payload()))
    llm = FakeLLM(_payload())
    models.generate("math", "Percentages", count=2, client=llm)
    assert "Question 0?" in llm.messages[1]["content"]


def test_answer_grades_and_records(ctx):
    q = models.generate("math", "Percentages", count=1,
                        client=FakeLLM(_payload(1, "B")))["questions"][0]
    hit = models.answer(q["id"], "b")
    assert hit["correct"] is True and hit["answer"] == "B"
    miss = models.answer(q["id"], "A")
    assert miss["correct"] is False
    assert models.answer(q["id"], "Z")["error"]
    assert models.answer(999999, "A")["error"]
    assert len(query("SELECT id FROM sat_attempts")) == 2


def test_progress_ranks_worst_skill_first(ctx):
    strong = models.generate("math", "Percentages", count=1,
                             client=FakeLLM(_payload(1, "B")))["questions"][0]
    weak = models.generate("math", "Probability", count=1,
                           client=FakeLLM(_payload(1, "B")))["questions"][0]
    models.answer(strong["id"], "B")
    models.answer(weak["id"], "A")
    models.answer(weak["id"], "C")

    data = models.progress()
    assert data["skills"][0]["skill"] == "Probability"
    assert data["skills"][0]["accuracy"] == 0.0
    assert data["sections"]["math"] == {"asked": 3, "right_count": 1, "accuracy": 33.3}
    assert "Percentages" not in data["untouched"]["math"]
    assert data["accuracy"] == 33.3


def test_weakest_skill_prefers_untouched_then_lowest(ctx):
    assert models.weakest_skill("reading") == models.skills("reading")[0]
    for skill in models.skills("math"):
        q = models.generate("math", skill, count=1,
                            client=FakeLLM(_payload(1, "B")))["questions"][0]
        models.answer(q["id"], "B" if skill != "Circles" else "A")
    assert models.weakest_skill("math") == "Circles"


def test_generate_defaults_to_the_weakest_skill(ctx):
    result = models.generate("reading", None, count=1, client=FakeLLM(_payload(1)))
    assert result["skill"] == models.skills("reading")[0]


def test_sat_page_and_apis(client):
    assert client.get("/sat").status_code == 200
    assert client.get("/api/sat/progress").get_json()["asked"] == 0
    # No API key in tests: generation reports it instead of reaching the network.
    r = client.post("/api/sat/generate", json={"section": "math"})
    assert r.status_code == 400 and "API key" in r.get_json()["error"]
    assert client.post("/api/sat/answer", json={"question_id": 1, "chosen": "A"}).status_code == 400


# --------------------------------------------------------------------------- #
# Answer-key cross-check: a second model solves every question independently.
# --------------------------------------------------------------------------- #
def test_verify_drops_questions_the_checker_disagrees_with(ctx):
    written = [{"stimulus": "", "prompt": "Volume?", "choices": ["a", "b", "c", "d"],
                "answer": "D", "explanation": "63 pi"},
               {"stimulus": "", "prompt": "Sum?", "choices": ["a", "b", "c", "d"],
                "answer": "B", "explanation": ""}]
    kept = models.verify(written, FakeLLM(_votes("C", "B")))
    assert [q["prompt"] for q in kept] == ["Sum?"]


def test_verify_keeps_the_set_when_the_checker_is_unreachable(ctx):
    class Dead(FakeLLM):
        def complete(self, messages, tools=None):
            from core.llm import LLMError
            raise LLMError("down")

    written = [{"stimulus": "", "prompt": "Q", "choices": ["a", "b", "c", "d"],
                "answer": "B", "explanation": ""}]
    assert models.verify(written, Dead("")) == written


def test_generate_stores_only_verified_questions(ctx):
    result = models.generate("math", "Percentages", count=2,
                             client=FakeLLM(_payload(2, "B")),
                             checker=FakeLLM(_votes("B", "A")))
    assert len(result["questions"]) == 1
    assert len(query("SELECT id FROM sat_questions")) == 1


def test_generate_reports_when_nothing_survives_the_check(ctx):
    result = models.generate("math", "Percentages", count=2,
                             client=FakeLLM(_payload(2, "B")),
                             checker=FakeLLM(_votes("A", "A")))
    assert "answer-key check" in result["error"]


# --------------------------------------------------------------------------- #
# Reset
# --------------------------------------------------------------------------- #
def test_reset_clears_attempts_and_tests_but_keeps_the_bank(ctx):
    q = models.generate("math", "Percentages", count=1, client=FakeLLM(_payload(1, "B")),
                        checker=FakeLLM(AGREE))["questions"][0]
    models.answer(q["id"], "B")
    models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))

    cleared = models.reset()
    assert cleared["attempts"] >= 1 and cleared["tests"] == 1
    assert models.progress()["asked"] == 0
    assert not models.tests() and models.open_test() is None
    assert query("SELECT id FROM sat_questions")          # bank survives


# --------------------------------------------------------------------------- #
# Full-length test
# --------------------------------------------------------------------------- #
def test_module_plan_matches_the_official_shape():
    assert len(models._plan("rw1")) == 27
    assert len(models._plan("math1")) == 22
    assert {sec for sec, _ in models._plan("rw1")} == {"reading", "writing"}
    assert {sec for sec, _ in models._plan("math2")} == {"math"}


def test_start_test_builds_module_one_without_the_answer_key(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    assert test["error"] is None
    assert test["module"] == "rw1" and test["minutes"] == 32
    assert test["questions"] and "answer" not in test["questions"][0]
    assert [q["position"] for q in test["questions"]] == list(range(1, len(test["questions"]) + 1))


def test_module_two_adapts_to_module_one(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    for q in test["questions"]:
        models.answer_item(q["item_id"], "A")            # all wrong
    assert models._difficulty_for(test["test_id"], "rw2") == "easy"

    execute("UPDATE sat_test_items SET correct = 1 WHERE test_id = %s", (test["test_id"],))
    assert models._difficulty_for(test["test_id"], "rw2") == "hard"


def test_answering_a_test_item_is_idempotent_and_feeds_the_ranking(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    item = test["questions"][0]
    first = models.answer_item(item["item_id"], "B")
    assert first["correct"] is True
    assert models.answer_item(item["item_id"], "A")["already"] is True
    assert models.progress()["asked"] == 1               # the second click added nothing


def test_reusing_the_bank_costs_no_extra_llm_calls(ctx):
    models.generate("math", "Percentages", count=4, client=FakeLLM(_payload(4, "B")),
                    checker=FakeLLM(AGREE))
    before = len(query("SELECT id FROM sat_questions"))
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    models.build_module(test["test_id"], "math1", client=FakeLLM(_payload(4, "B")),
                        checker=FakeLLM(AGREE))
    served = query("SELECT question_id FROM sat_test_items WHERE module = 'math1'")
    assert before <= len(query("SELECT id FROM sat_questions"))
    # The four medium Percentages questions written above were served, not rewritten.
    assert len(served) >= 4


def test_building_the_same_module_twice_serves_the_same_questions(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    again = models.build_module(test["test_id"], "rw1", client=FakeLLM(_payload(4, "B")))
    assert [q["item_id"] for q in again["questions"]] == [q["item_id"] for q in test["questions"]]


def test_score_scales_and_applies_the_adaptive_cap(ctx):
    assert models._scale(0, 10, False) == 200
    assert models._scale(10, 10, False) == 600          # easy module 2 caps out
    assert models._scale(10, 10, True) == 800
    assert models._scale(0, 10, True) == 400            # hard module 2 floors
    assert models._scale(0, 0, False) == 200


def test_finish_test_records_both_section_scores(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    for q in test["questions"]:
        models.answer_item(q["item_id"], "B")
    result = models.finish_test(test["test_id"])
    assert result["rw"]["score"] == 800 and result["rw"]["hard_track"] is True
    assert result["total"] == result["rw"]["score"] + result["math"]["score"]
    row = models.tests()[0]
    assert row["rw_score"] == 800 and row["total"] == result["total"]
    assert models.open_test() is None                   # finished tests do not resume


def test_open_test_points_at_the_module_still_owed(ctx):
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    assert models.open_test() == {"test_id": test["test_id"], "module": "rw1", "started": True}
    for q in test["questions"]:
        models.answer_item(q["item_id"], "B")
    assert models.open_test()["module"] == "rw2"


def test_test_apis_refuse_without_a_key(client):
    assert client.post("/api/sat/test").status_code == 400
    assert client.post("/api/sat/test/1/module/rw1").status_code == 400
    assert client.post("/api/sat/test/answer", json={"item_id": 1, "chosen": "A"}).status_code == 400
    assert client.post("/api/sat/reset").get_json() == {"attempts": 0, "tests": 0}


def test_chart_plots_finished_tests_against_the_target(ctx):
    assert models.chart() is None                        # nothing finished yet
    test = models.start_test(client=FakeLLM(_payload(4, "B")), checker=FakeLLM(AGREE))
    for q in test["questions"]:
        models.answer_item(q["item_id"], "B")
    result = models.finish_test(test["test_id"])
    data = models.chart()
    assert data["target"] == models.TARGET == 1530
    assert data["latest"] == data["best"] == result["total"]
    assert data["gap"] == max(0, models.TARGET - result["total"]) == result["gap"]
    # One test: a single centred point, plotted below the target line (y grows down).
    assert len(data["points"]) == 1 and data["points"][0]["x"] == 150
    assert 0 <= data["target_y"] < data["points"][0]["y"] <= 120
