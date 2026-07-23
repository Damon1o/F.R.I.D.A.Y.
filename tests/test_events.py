import pytest

from pages.calendar import models
from pages.calendar.models import ValidationError


def test_create_and_get(ctx):
    e = models.create_event({"title": "Standup", "start_at": "2026-07-22T09:00"})
    assert e["id"] and e["title"] == "Standup"
    assert models.get_event(e["id"])["title"] == "Standup"


def test_empty_title_rejected(ctx):
    with pytest.raises(ValidationError):
        models.create_event({"title": "  ", "start_at": "2026-07-22T09:00"})


def test_bad_datetime_rejected(ctx):
    with pytest.raises(ValidationError):
        models.create_event({"title": "X", "start_at": "not-a-date"})


def test_end_before_start_rejected(ctx):
    with pytest.raises(ValidationError):
        models.create_event({"title": "X", "start_at": "2026-07-22T10:00", "end_at": "2026-07-22T09:00"})


def test_list_range_filter(ctx):
    models.create_event({"title": "A", "start_at": "2026-07-01T09:00"})
    models.create_event({"title": "B", "start_at": "2026-07-20T09:00"})
    got = models.list_events(start="2026-07-15T00:00", end="2026-07-31T00:00")
    assert [e["title"] for e in got] == ["B"]


def test_update_and_delete(ctx):
    e = models.create_event({"title": "Old", "start_at": "2026-07-22T09:00"})
    assert models.update_event(e["id"], {"title": "New"})["title"] == "New"
    assert models.delete_event(e["id"]) is True
    assert models.get_event(e["id"]) is None
    assert models.update_event(9999, {"title": "x"}) is None


# ---- endpoint smoke ----

def test_api_crud(client):
    r = client.post("/api/events", json={"title": "Meet", "start_at": "2026-07-22T09:00"})
    assert r.status_code == 201
    eid = r.get_json()["id"]

    assert client.get("/api/events").status_code == 200
    assert client.patch(f"/api/events/{eid}", json={"location": "Room 1"}).get_json()["location"] == "Room 1"
    assert client.delete(f"/api/events/{eid}").status_code == 204
    assert client.delete(f"/api/events/{eid}").status_code == 404


def test_api_bad_body_400(client):
    assert client.post("/api/events", json={"start_at": "2026-07-22T09:00"}).status_code == 400
