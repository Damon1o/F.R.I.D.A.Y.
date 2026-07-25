"""Dashboard: read-only overview of the week — stats, charts, upcoming.

All data is computed here (no client JS). The bar chart is CSS heights; the line
chart is a server-built SVG polyline. Adding events/tasks lives on their own pages
and in the F.R.I.D.A.Y. panel — the dashboard only displays.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template

from pages.calendar.models import list_events
from pages.todos.models import list_todos

dashboard_bp = Blueprint("dashboard", __name__)

_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_of(iso: str) -> str:
    """Local calendar date (YYYY-MM-DD). completed_at is UTC, so convert; naive stays as-is."""
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone()
    return dt.date().isoformat()


def _bars(counts: list[int]) -> list[dict]:
    top = max(counts) or 1
    return [{"pct": round(c / top * 100)} for c in counts]


@dashboard_bp.route("/")
def index():
    today = date.today()
    now = datetime.now()

    start = datetime.combine(today, datetime.min.time()).isoformat()
    end = datetime.combine(today, datetime.max.time()).isoformat()
    events_today = list_events(start=start, end=end)
    open_todos = list_todos(done=False)
    all_todos = list_todos()

    overdue = sum(1 for t in open_todos if t["due_at"] and t["due_at"] < now.isoformat())
    due_today = sum(1 for t in open_todos if _day_of(t["due_at"]) == today.isoformat())

    # This week (Mon..Sun): events scheduled per weekday.
    monday = today - timedelta(days=today.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    week_events = list_events(
        start=monday.isoformat(),
        end=datetime.combine(week_days[-1], datetime.max.time()).isoformat(),
    )
    events_by_day = [sum(1 for e in week_events if _day_of(e["start_at"]) == d.isoformat())
                     for d in week_days]

    # Last 7 days (rolling): tasks completed.
    last7 = {(today - timedelta(days=i)).isoformat() for i in range(7)}
    completed_week = sum(1 for t in all_todos if _day_of(t["completed_at"]) in last7)

    # Next events from now onward.
    upcoming = list_events(start=now.isoformat())[:6]

    return render_template(
        "dashboard.html",
        today=today,
        stats={
            "events": len(events_today),
            "open": len(open_todos),
            "overdue": overdue,
            "completed": completed_week,
        },
        week=list(zip(_WD, _bars(events_by_day), events_by_day)),
        breakdown=[
            ("Open tasks", len(open_todos)),
            ("Due today", due_today),
            ("Overdue", overdue),
            ("Completed (7d)", completed_week),
        ],
        upcoming=upcoming,
    )
