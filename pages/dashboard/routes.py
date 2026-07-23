"""Dashboard: today's agenda (events + open todos) with quick-add."""
from datetime import date, datetime

from flask import Blueprint, render_template

from pages.calendar.models import list_events
from pages.todos.models import list_todos

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    today = date.today()
    start = datetime.combine(today, datetime.min.time()).isoformat()
    end = datetime.combine(today, datetime.max.time()).isoformat()
    events = list_events(start=start, end=end)
    open_todos = list_todos(done=False)
    now = datetime.now().isoformat()
    overdue = sum(1 for t in open_todos if t["due_at"] and t["due_at"] < now)
    return render_template(
        "dashboard.html",
        events=events,
        todos=open_todos,
        today=today,
        stats={"events": len(events), "open": len(open_todos), "overdue": overdue},
    )
