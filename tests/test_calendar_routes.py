def test_calendar_page_renders(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"calendar" in response.data.lower()
    assert b'id="calendar-fab"' in response.data


def test_calendar_events_api_returns_json_list(client):
    response = client.get(
        "/calendar/api/events?start=2026-08-01T00:00:00&end=2026-08-31T23:59:59"
    )
    assert response.status_code == 200
    assert response.get_json() == []


def test_calendar_skill_is_registered_with_tools():
    from core.context_loader import SKILL_REGISTRY

    assert "calendar" in SKILL_REGISTRY
    tool_names = {tool["name"] for tool in SKILL_REGISTRY["calendar"]["tools"]}
    assert tool_names == {"add_event", "update_event", "delete_event", "list_events"}


def test_calendar_tools_are_registered_in_dispatch():
    from pages.chat.routes import TOOL_DISPATCH

    assert set(["add_event", "update_event", "delete_event", "list_events"]).issubset(
        TOOL_DISPATCH.keys()
    )
