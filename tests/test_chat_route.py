import json
from unittest.mock import patch

from core.providers.base import ProviderResponse


def test_chat_endpoint_returns_plain_text_reply(client):
    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "haiku", "skills": []}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_reply_response = ProviderResponse(
        text="Sure, done!", input_tokens=30, output_tokens=10, stop_reason="end_turn"
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[fake_classify_response, fake_reply_response],
    ):
        response = client.post(
            "/api/chat",
            json={"message": "hello", "active_page": "calendar"},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["reply"] == "Sure, done!"
    assert data["total_tokens"] == 55
    assert data["budget_warning"] is False


def test_chat_endpoint_executes_tool_call_then_replies(client):
    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "sonnet", "skills": ["calendar"]}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_tool_call_response = ProviderResponse(
        text="",
        tool_calls=[
            {
                "id": "tool_1",
                "name": "add_event",
                "input": {
                    "title": "Dentist",
                    "start_datetime": "2026-08-04T15:00:00",
                    "end_datetime": "2026-08-04T15:30:00",
                },
            }
        ],
        input_tokens=40,
        output_tokens=20,
        stop_reason="tool_use",
    )
    fake_final_response = ProviderResponse(
        text="Added your dentist appointment.",
        input_tokens=60,
        output_tokens=15,
        stop_reason="end_turn",
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[
            fake_classify_response,
            fake_tool_call_response,
            fake_final_response,
        ],
    ):
        response = client.post(
            "/api/chat",
            json={"message": "add a dentist appt next tuesday 3pm", "active_page": "calendar"},
        )

    data = response.get_json()
    assert data["reply"] == "Added your dentist appointment."
    assert data["total_tokens"] == 10 + 5 + 40 + 20 + 60 + 15


def test_chat_endpoint_flags_budget_warning_when_over_threshold(client, app):
    app.config["TOKEN_BUDGET_WARNING"] = 10

    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "haiku", "skills": []}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_reply_response = ProviderResponse(
        text="Hi!", input_tokens=10, output_tokens=5, stop_reason="end_turn"
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[fake_classify_response, fake_reply_response],
    ):
        response = client.post(
            "/api/chat", json={"message": "hi", "active_page": "calendar"}
        )

    assert response.get_json()["budget_warning"] is True
