from datetime import datetime

from core.db import db
from pages.calendar.models import Event


def test_event_round_trips_through_db(app):
    event = Event(
        title="Dentist",
        start_datetime=datetime(2026, 8, 4, 15, 0),
        end_datetime=datetime(2026, 8, 4, 15, 30),
        recurrence_rule="none",
    )
    db.session.add(event)
    db.session.commit()

    fetched = Event.query.filter_by(title="Dentist").one()
    assert fetched.recurrence_rule == "none"
    assert fetched.to_dict()["title"] == "Dentist"
