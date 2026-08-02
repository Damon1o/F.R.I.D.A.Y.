"""Week view — the client is new but the data contract is the API window query."""
from pages.calendar import models as events

# Sun 2026-07-26 .. Sat 2026-08-01
WEEK = ("2026-07-26T00:00", "2026-08-01T23:59:59.999999")


def test_window_excludes_events_outside_the_week(ctx):
    events.create_event({"title": "inside", "start_at": "2026-07-29T14:00:00"})
    events.create_event({"title": "before", "start_at": "2026-07-25T14:00:00"})
    events.create_event({"title": "after", "start_at": "2026-08-02T09:00:00"})
    titles = [e["title"] for e in events.list_events(*WEEK)]
    assert titles == ["inside"]


def test_last_minute_of_the_week_is_included(ctx):
    events.create_event({"title": "late", "start_at": "2026-08-01T23:59:00"})
    assert [e["title"] for e in events.list_events(*WEEK)] == ["late"]


def test_recurring_master_expands_once_per_week(ctx):
    events.create_event({"title": "Standup", "start_at": "2026-07-20T09:00:00",
                         "end_at": "2026-07-20T09:15:00", "rrule": "FREQ=WEEKLY"})
    occ = events.list_events(*WEEK)
    assert [e["start_at"] for e in occ] == ["2026-07-27T09:00:00"]
    assert occ[0]["end_at"] == "2026-07-27T09:15:00"      # duration survives, blocks size correctly


def test_skipped_occurrence_absent_from_the_week(ctx):
    m = events.create_event({"title": "Standup", "start_at": "2026-07-20T09:00:00",
                             "rrule": "FREQ=WEEKLY"})
    events.skip_occurrence(m["id"], "2026-07-27T09:00:00")
    assert events.list_events(*WEEK) == []


def test_calendar_page_ships_the_week_view(client):
    html = client.get("/calendar").data
    # The right-click menu itself is app-wide now and built by menu.js.
    for marker in (b'id="cal-week"', b'id="cal-hours-inner"', b"menu.js", b"calendar-week.js"):
        assert marker in html
