"""Day-before SMS reminders. One message per event and per deadline landing tomorrow.

Driven by a once-a-day cron (see vercel.json -> /api/cron/reminders). Silent
unless the `reminders_sms` setting is on and `reminder_phone` is set.
"""
from datetime import datetime, timedelta

from core.clock import now, tz
from core.db import query
from pages.calendar.models import list_events
from pages.friday.sms import send_sms
from pages.todos.models import list_todos

LAST_RUN_KEY = "reminders_last_run"


def _when(iso: str, all_day: bool = False) -> str:
    """'Tomorrow' or 'Tomorrow at 5:00 PM'. %-I/%#I are not portable, so format by hand."""
    t = datetime.fromisoformat(iso)
    if all_day or (t.hour == 0 and t.minute == 0):
        return "tomorrow"
    return f"tomorrow at {(t.hour % 12) or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def lines() -> list[str]:
    """One reminder text per event / open deadline on tomorrow's local date."""
    day = (now() + timedelta(days=1)).date()
    zone = tz()
    start = datetime.combine(day, datetime.min.time()).replace(tzinfo=zone).isoformat()
    end = datetime.combine(day, datetime.max.time()).replace(tzinfo=zone).isoformat()

    out = []
    for e in list_events(start=start, end=end):
        where = f" ({e['location']})" if e.get("location") else ""
        out.append(f"Reminder: {e['title']} is {_when(e['start_at'], e['all_day'])}{where}")
    for t in list_todos(done=False):
        if t["due_at"] and t["due_at"][:10] == day.isoformat():
            out.append(f"Reminder: \"{t['title']}\" is due {_when(t['due_at'])}")
    return out


def run(force: bool = False) -> dict:
    """Send tomorrow's reminders. Once per local day unless `force`."""
    # Local import: pages.settings.routes imports this module for the cron route.
    from pages.settings.routes import get_prefs, _set_pref

    prefs = get_prefs()
    if prefs["reminders_sms"] != "true":
        return {"skipped": "reminders are off"}
    if not prefs["reminder_phone"]:
        return {"skipped": "no reminder phone number set"}

    today = now().date().isoformat()
    last = query("SELECT value FROM settings WHERE key = %s", (LAST_RUN_KEY,), one=True)
    if not force and last and last["value"] == today:
        return {"skipped": "already ran today"}

    results = [send_sms(prefs["reminder_phone"], line) for line in lines()]
    _set_pref(LAST_RUN_KEY, today)
    errors = [r["error"] for r in results if "error" in r]
    return {"date": today, "sent": len(results) - len(errors), "errors": errors}
