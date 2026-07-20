import json
from dataclasses import dataclass

from core.providers.base import Provider

TIER_MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
}

_CLASSIFIER_SYSTEM_PROMPT = """You are a request router for a personal AI assistant.
Given the user's message and which page of the app they're on, respond with ONLY
a JSON object (no other text) of the form:
{"tier": "haiku" | "sonnet" | "opus", "skills": ["<page-name>", ...]}

Tier guidance:
- "haiku": simple, unambiguous single-step requests
- "sonnet": default tier for most real work, multi-step reasoning, drafting
- "opus": genuinely complex, high-stakes, or multi-constraint planning

"skills" should list which page(s) this request needs tools/context for
(e.g. "calendar"). If none apply, use an empty list.
"""


@dataclass
class RouteDecision:
    tier: str
    skills: list[str]


def classify(provider: Provider, user_message: str, active_page: str) -> RouteDecision:
    response = provider.complete(
        system=_CLASSIFIER_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Active page: {active_page}\nMessage: {user_message}",
            }
        ],
        tools=None,
        model=TIER_MODELS["haiku"],
    )

    try:
        parsed = json.loads(response.text)
        tier = parsed.get("tier", "sonnet")
        skills = parsed.get("skills", [])
        if tier not in TIER_MODELS:
            tier = "sonnet"
        return RouteDecision(tier=tier, skills=skills)
    except (json.JSONDecodeError, AttributeError):
        return RouteDecision(tier="sonnet", skills=[])
