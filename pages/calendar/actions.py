from datetime import datetime

from core.db import db
from pages.calendar.models import Event


def add_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    recurrence_rule: str = "none",
    notes: str | None = None,
) -> dict:
    event = Event(
        title=title,
        start_datetime=datetime.fromisoformat(start_datetime),
        end_datetime=datetime.fromisoformat(end_datetime),
        recurrence_rule=recurrence_rule,
        notes=notes,
    )
    db.session.add(event)
    db.session.commit()
    return event.to_dict()


def update_event(event_id: int, **fields) -> dict | None:
    event = db.session.get(Event, event_id)
    if event is None:
        return None

    for key, value in fields.items():
        if key in ("start_datetime", "end_datetime") and value is not None:
            value = datetime.fromisoformat(value)
        setattr(event, key, value)

    db.session.commit()
    return event.to_dict()


def delete_event(event_id: int) -> bool:
    event = db.session.get(Event, event_id)
    if event is None:
        return False
    db.session.delete(event)
    db.session.commit()
    return True


def list_events(start_range: str, end_range: str) -> list[dict]:
    start = datetime.fromisoformat(start_range)
    end = datetime.fromisoformat(end_range)
    events = (
        Event.query.filter(Event.start_datetime >= start, Event.start_datetime <= end)
        .order_by(Event.start_datetime)
        .all()
    )
    return [event.to_dict() for event in events]
