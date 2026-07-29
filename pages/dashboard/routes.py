"""Dashboard: read-only overview of the week — stats, charts, upcoming.

All data is computed here (no client JS). The bar chart is CSS heights; the line
chart is a server-built SVG polyline. Adding events/tasks lives on their own pages
and in the F.R.I.D.A.Y. panel — the dashboard only displays.
"""
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template

from core.clock import now, to_local, tz
from pages.calendar.models import list_events
from pages.friday.weather import get_weather
from pages.todos.models import list_todos

dashboard_bp = Blueprint("dashboard", __name__)

_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_of(iso: str) -> str:
    """Local calendar date (YYYY-MM-DD). completed_at is UTC, so convert; naive stays as-is."""
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = to_local(dt)
    return dt.date().isoformat()


def _bars(counts: list[int]) -> list[dict]:
    top = max(counts) or 1
    return [{"pct": round(c / top * 100)} for c in counts]


@dashboard_bp.route("/")
def index():
    user_now = now()
    today = user_now.date()
    user_tz = tz()

    open_todos = list_todos(done=False)
    all_todos = list_todos()

    # Overdue: due_at < now (both in user tz; due_at stored as local wall time)
    overdue = sum(1 for t in open_todos if t["due_at"] and t["due_at"] < user_now.isoformat())
    due_today = sum(1 for t in open_todos if _day_of(t["due_at"]) == today.isoformat())

    # This week (Mon..Sun) in user tz
    monday = today - timedelta(days=today.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    week_start = datetime.combine(monday, datetime.min.time()).replace(tzinfo=user_tz).isoformat()
    week_end = datetime.combine(week_days[-1], datetime.max.time()).replace(tzinfo=user_tz).isoformat()
    week_events = list_events(start=week_start, end=week_end)
    events_by_day = [
        sum(1 for e in week_events if _day_of(e["start_at"]) == d.isoformat())
        for d in week_days
    ]

    # Last 7 days (rolling): tasks completed
    last7 = {(today - timedelta(days=i)).isoformat() for i in range(7)}
    completed_week = sum(1 for t in all_todos if _day_of(t["completed_at"]) in last7)

    # Next events from now onward
    upcoming = list_events(start=user_now.isoformat())[:6]

    return render_template(
        "dashboard.html",
        today=today,
        week=list(zip(_WD, _bars(events_by_day), events_by_day)),
        breakdown=[
            ("Open tasks", len(open_todos)),
            ("Due today", due_today),
            ("Overdue", overdue),
            ("Completed (7d)", completed_week),
        ],
        upcoming=upcoming,
    )


@dashboard_bp.route("/api/weather")
def weather_api():
    """Current weather + 3-day forecast via Open-Meteo (keyless)."""
    return jsonify(get_weather())
