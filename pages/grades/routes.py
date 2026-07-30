"""Grades: /grades page (throttled sync on load) + forced sync and LLM readout APIs."""
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from pages.calendar.models import ValidationError
from pages.grades import gpa, models

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
    official = models.official_gpa()
    result = gpa.compute()
    return render_template(
        "grades.html",
        configured=state["configured"],
        synced_ago=ago(state["synced_at"]),
        sync_error=sync["error"] or state["error"],
        ranking=models.ranking(),
        alerts=models.alerts(),
        gpa=result,
        official_gpa=official,
        gpa_models=gpa.compare(official, result),
        levels=gpa.LEVELS,
        gpa_bonus=gpa.BONUS,
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


@grades_bp.route("/api/gpa", methods=["GET"])
def gpa_get():
    official = models.official_gpa()
    result = gpa.compute()
    return jsonify({"gpa": result, "official": official,
                    "models": gpa.compare(official, result)})


@grades_bp.route("/api/gpa/courses", methods=["POST"])
def gpa_add_course():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(gpa.add_manual(
            body.get("year"), body.get("name"), body.get("final_pct"),
            body.get("level", "regular"), body.get("credits", 1),
        )), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@grades_bp.route("/api/gpa/courses/<int:row_id>", methods=["DELETE"])
def gpa_delete_course(row_id):
    return ("", 204) if gpa.delete_manual(row_id) else (jsonify({"error": "not found"}), 404)


@grades_bp.route("/api/gpa/level", methods=["POST"])
def gpa_set_level():
    body = request.get_json(silent=True) or {}
    try:
        level = gpa.set_level(body.get("name"), body.get("level"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": body.get("name"), "level": level, "gpa": gpa.compute()})


@grades_bp.route("/api/gpa/official", methods=["POST"])
def gpa_set_official():
    body = request.get_json(silent=True) or {}
    try:
        official = models.set_official_gpa(body.get("official"))
    except (TypeError, ValueError):
        return jsonify({"error": "official must be a number"}), 400
    return jsonify({"official": official, "models": gpa.compare(official)})
