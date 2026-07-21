from pages.calendar.actions import (
    add_event,
    delete_event,
    list_events,
    update_event,
)


def test_add_event_creates_row(app):
    result = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    assert result["title"] == "Dentist"
    assert result["recurrence_rule"] == "none"


def test_list_events_filters_by_range(app):
    add_event(
        title="In range",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    add_event(
        title="Out of range",
        start_datetime="2026-09-01T09:00:00",
        end_datetime="2026-09-01T09:30:00",
    )

    results = list_events(
        start_range="2026-08-01T00:00:00", end_range="2026-08-31T23:59:59"
    )

    titles = [event["title"] for event in results]
    assert titles == ["In range"]


def test_update_event_changes_fields(app):
    created = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    updated = update_event(created["id"], recurrence_rule="monthly")
    assert updated["recurrence_rule"] == "monthly"


def test_update_event_returns_none_for_missing_id(app):
    assert update_event(9999, title="x") is None


def test_delete_event_removes_row(app):
    created = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    assert delete_event(created["id"]) is True
    assert list_events(
        start_range="2026-08-01T00:00:00", end_range="2026-08-31T23:59:59"
    ) == []


def test_delete_event_returns_false_for_missing_id(app):
    assert delete_event(9999) is False
