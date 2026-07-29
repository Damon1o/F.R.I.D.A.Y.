"""Day-before reminders: one SMS per event/deadline, off by default, cron auth. SMS always faked."""
from datetime import timedelta

import core.reminders as reminders
from core.clock import now
from pages.calendar.models import create_event
from pages.settings.routes import _set_pref
from pages.todos.models import create_todo


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(reminders, "send_sms", lambda to, body: sent.append((to, body)) or {"sent": True})
    return sent


def _enable():
    _set_pref("reminders_sms", "true")
    _set_pref("reminder_phone", "+12125550147")


def _tomorrow(hour=0, minute=0):
    return (now() + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def test_off_by_default_sends_nothing(ctx, monkeypatch):
    sent = _capture(monkeypatch)
    create_event({"title": "Standup", "start_at": _tomorrow(9)})
    assert "skipped" in reminders.run()
    assert sent == []


def test_one_message_per_event_and_deadline(ctx, monkeypatch):
    sent = _capture(monkeypatch)
    _enable()
    create_event({"title": "Dentist", "start_at": _tomorrow(9, 30), "location": "Main St"})
    create_todo({"title": "File taxes", "due_at": _tomorrow(17)})
    create_event({"title": "Next week", "start_at": (now() + timedelta(days=7)).isoformat()})
    create_todo({"title": "Someday", "due_at": (now() + timedelta(days=3)).isoformat()})

    res = reminders.run()
    assert res["sent"] == 2 and res["errors"] == []
    bodies = sorted(b for _, b in sent)
    assert bodies == [
        'Reminder: "File taxes" is due tomorrow at 5:00 PM',
        "Reminder: Dentist is tomorrow at 9:30 AM (Main St)",
    ]
    assert all(to == "+12125550147" for to, _ in sent)


def test_all_day_and_midnight_drop_the_time(ctx, monkeypatch):
    sent = _capture(monkeypatch)
    _enable()
    create_event({"title": "Birthday", "start_at": _tomorrow(), "all_day": True})
    create_todo({"title": "Rent", "due_at": _tomorrow()})
    reminders.run()
    assert sorted(b for _, b in sent) == [
        'Reminder: "Rent" is due tomorrow',
        "Reminder: Birthday is tomorrow",
    ]


def test_runs_once_per_day(ctx, monkeypatch):
    sent = _capture(monkeypatch)
    _enable()
    create_event({"title": "Standup", "start_at": _tomorrow(9)})
    assert reminders.run()["sent"] == 1
    assert "skipped" in reminders.run()
    assert reminders.run(force=True)["sent"] == 1
    assert len(sent) == 2


def test_done_todos_are_not_reminded(ctx, monkeypatch):
    from pages.todos.models import update_todo

    sent = _capture(monkeypatch)
    _enable()
    t = create_todo({"title": "Already done", "due_at": _tomorrow(10)})
    update_todo(t["id"], {"done": True})
    assert reminders.run()["sent"] == 0
    assert sent == []


def test_cron_endpoint_requires_secret(client, monkeypatch):
    assert client.get("/api/cron/reminders").status_code == 401  # no CRON_SECRET configured
    monkeypatch.setattr("config.Config.CRON_SECRET", "s3cret")
    assert client.get("/api/cron/reminders", headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.get("/api/cron/reminders", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and "skipped" in r.get_json()


def test_bad_phone_rejected(client):
    r = client.post("/api/settings/ui", json={"reminder_phone": "555-1234"})
    assert r.status_code == 400
    ok = client.post("/api/settings/ui", json={"reminder_phone": "+1 212-555-0147"})
    assert ok.get_json()["reminder_phone"] == "+12125550147"
