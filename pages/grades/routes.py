"""Grades: /grades page (throttled sync on load) + forced sync and LLM readout APIs."""
from datetime import datetime

from flask import Blueprint, jsonify, render_template

from pages.grades import models

grades_bp = Blueprint("grades", __name__)


def ago(ts: str | None) -> str | None:
    """'14m ago' from a stored UTC timestamp. None when never synced."""
    if not ts:
        return None
    try:
        delta = models._utcnow() - datetime.strptime(ts[:19], models.TS_FMT)
    except ValueError:
        return ts
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    if mins < 1440:
        return f"{mins // 60}h ago"
    return f"{mins // 1440}d ago"


@grades_bp.route("/grades")
def grades_page():
    sync = models.sync()  # throttled to once per 2h; never raises
    state = models.status()
    return render_template(
        "grades.html",
        configured=state["configured"],
        synced_ago=ago(state["synced_at"]),
        sync_error=sync["error"] or state["error"],
        ranking=models.ranking(),
        alerts=models.alerts(),
    )


@grades_bp.route("/api/grades/sync", methods=["POST"])
def grades_sync():
    result = models.sync(force=True)
    if not result["configured"]:
        return jsonify({"error": "Infinite Campus is not configured."}), 400
    result["synced_ago"] = ago(result["synced_at"])
    return jsonify(result)


@grades_bp.route("/api/grades/analysis", methods=["POST"])
def grades_analysis():
    result = models.analysis()
    return jsonify(result), (200 if result["text"] else 400)
