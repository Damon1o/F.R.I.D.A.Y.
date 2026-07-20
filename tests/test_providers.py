from unittest.mock import MagicMock, patch

import pytest

from core.providers.anthropic_provider import AnthropicProvider
from core.providers.openai_provider import OpenAIProvider


def _fake_anthropic_message():
    text_block = MagicMock(type="text", text="Hello there")
    usage = MagicMock(input_tokens=12, output_tokens=8)
    message = MagicMock(content=[text_block], usage=usage, stop_reason="end_turn")
    return message


def test_anthropic_provider_returns_text_response():
    provider = AnthropicProvider(api_key="fake-key")
    with patch.object(
        provider.client.messages, "create", return_value=_fake_anthropic_message()
    ):
        result = provider.complete(
            system="You are helpful.",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="claude-haiku-4-5",
        )

    assert result.text == "Hello there"
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.tool_calls == []


def test_anthropic_provider_extracts_tool_calls():
    tool_block = MagicMock(type="tool_use", id="tool_1", input={"title": "Dentist"})
    tool_block.name = "add_event"
    usage = MagicMock(input_tokens=20, output_tokens=15)
    message = MagicMock(content=[tool_block], usage=usage, stop_reason="tool_use")

    provider = AnthropicProvider(api_key="fake-key")
    with patch.object(provider.client.messages, "create", return_value=message):
        result = provider.complete(
            system="You are helpful.",
            messages=[{"role": "user", "content": "add a dentist appt"}],
            tools=[{"name": "add_event"}],
            model="claude-sonnet-4-5",
        )

    assert result.tool_calls == [
        {"id": "tool_1", "name": "add_event", "input": {"title": "Dentist"}}
    ]
    assert result.stop_reason == "tool_use"


def test_openai_provider_raises_not_implemented():
    provider = OpenAIProvider(api_key="fake-key")
    with pytest.raises(NotImplementedError):
        provider.complete(system="x", messages=[], tools=None, model="gpt-4o")
