from core.context_loader import build_context, register_skill

BASE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant running inside a desktop web app."
)


def test_build_context_with_no_skills_returns_base_prompt():
    context = build_context([])
    assert context["system_prompt"] == BASE_SYSTEM_PROMPT
    assert context["tools"] == []


def test_build_context_includes_registered_skill():
    register_skill(
        "example",
        system_prompt="You can manage example items.",
        tools=[{"name": "add_example", "description": "add one"}],
    )
    context = build_context(["example"])
    assert "You can manage example items." in context["system_prompt"]
    assert context["tools"] == [{"name": "add_example", "description": "add one"}]


def test_build_context_ignores_unknown_skill_names():
    context = build_context(["does-not-exist"])
    assert context["system_prompt"] == BASE_SYSTEM_PROMPT
    assert context["tools"] == []
