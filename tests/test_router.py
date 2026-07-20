import json
from unittest.mock import MagicMock

from core.providers.base import ProviderResponse
from core.router import classify


def _provider_returning(tier: str, skills: list[str]):
    provider = MagicMock()
    provider.complete.return_value = ProviderResponse(
        text=json.dumps({"tier": tier, "skills": skills}),
        tool_calls=[],
        input_tokens=50,
        output_tokens=10,
        stop_reason="end_turn",
    )
    return provider


def test_classify_returns_haiku_for_simple_request():
    provider = _provider_returning("haiku", ["calendar"])
    decision = classify(provider, "add lunch with Sam tomorrow at noon", "calendar")
    assert decision.tier == "haiku"
    assert decision.skills == ["calendar"]


def test_classify_returns_opus_for_complex_request():
    provider = _provider_returning("opus", ["calendar"])
    decision = classify(
        provider,
        "reorganize my next three weeks of appointments around a new work trip",
        "calendar",
    )
    assert decision.tier == "opus"


def test_classify_falls_back_to_sonnet_on_bad_json():
    provider = MagicMock()
    provider.complete.return_value = ProviderResponse(
        text="not json", tool_calls=[], input_tokens=5, output_tokens=5
    )
    decision = classify(provider, "hello", "calendar")
    assert decision.tier == "sonnet"
    assert decision.skills == []


def test_classify_falls_back_to_sonnet_on_none_response_text():
    provider = MagicMock()
    provider.complete.return_value = ProviderResponse(
        text=None, tool_calls=[], input_tokens=5, output_tokens=5
    )
    decision = classify(provider, "hello", "calendar")
    assert decision.tier == "sonnet"
    assert decision.skills == []
