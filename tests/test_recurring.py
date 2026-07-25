"""Spec L — recurring events: rrule storage, window expansion, EXDATE skip."""
import pytest

from pages.calendar import models as events
from pages.calendar.models import ValidationError
from pages.friday.tools import dispatch

# 2026-07-20 is a Monday.
MASTER = {"title": "Standup", "start_at": "2026-07-20T09:00:00",
          "end_at": "2026-07-20T09:15:00", "rrule": "FREQ=WEEKLY"}
WIN = ("2026-07-20T00:00:00", "2026-08-10T23:59:59")


def test_weekly_expands_within_window(ctx):
    events.create_event(MASTER)
    occ = events.list_events(*WIN)
    starts = [e["start_at"][:10] for e in occ]
    assert starts == ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10"]
    # duration preserved (15 min), occurrence_of points at the master
    assert occ[0]["end_at"] == "2026-07-20T09:15:00"
    assert all(e["occurrence_of"] for e in occ)


def test_no_window_returns_master_unexpanded(ctx):
    events.create_event(MASTER)
    rows = events.list_events()
    assert len(rows) == 1 and rows[0]["rrule"] == "FREQ=WEEKLY"


def test_skip_occurrence_hides_one(ctx):
    m = events.create_event(MASTER)
    assert events.skip_occurrence(m["id"], "2026-07-27T09:00:00") is True
    starts = [e["start_at"][:10] for e in events.list_events(*WIN)]
    assert "2026-07-27" not in starts and len(starts) == 3


def test_skip_non_recurring_fails(ctx):
    m = events.create_event({"title": "one-off", "start_at": "2026-07-20T09:00:00"})
    assert events.skip_occurrence(m["id"], "2026-07-20T09:00:00") is False


def test_invalid_rrule_rejected(ctx):
    with pytest.raises(ValidationError):
        events.create_event({"title": "bad", "start_at": "2026-07-20T09:00:00", "rrule": "NOTAREALRULE"})


def test_non_recurring_events_still_listed(ctx):
    events.create_event({"title": "plain", "start_at": "2026-07-21T10:00:00"})
    rows = events.list_events(*WIN)
    assert any(e["title"] == "plain" for e in rows)


def test_skip_tool_and_endpoint(ctx, client):
    m = events.create_event(MASTER)
    assert dispatch("skip_occurrence", {"event_id": m["id"], "occurrence": "2026-08-03T09:00:00"})["skipped"]
    assert client.post(f"/api/events/{m['id']}/skip",
                       json={"occurrence": "2026-08-10T09:00:00"}).status_code == 204
    assert len(events.list_events(*WIN)) == 2  # 07-20, 07-27 remain
