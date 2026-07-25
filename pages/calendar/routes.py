"""Calendar: month page + /api/events CRUD."""
from flask import Blueprint, jsonify, render_template, request

from pages.calendar import models
from pages.calendar.models import ValidationError

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/calendar")
def calendar_page():
    return render_template("calendar.html")


@calendar_bp.route("/api/events", methods=["GET"])
def events_list():
    return jsonify(models.list_events(request.args.get("from"), request.args.get("to")))


@calendar_bp.route("/api/events", methods=["POST"])
def events_create():
    try:
        return jsonify(models.create_event(request.get_json(silent=True) or {})), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@calendar_bp.route("/api/events/<int:event_id>", methods=["PATCH"])
def events_update(event_id):
    try:
        event = models.update_event(event_id, request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return (jsonify(event), 200) if event else (jsonify({"error": "not found"}), 404)


@calendar_bp.route("/api/events/<int:event_id>", methods=["DELETE"])
def events_delete(event_id):
    return ("", 204) if models.delete_event(event_id) else (jsonify({"error": "not found"}), 404)


@calendar_bp.route("/api/events/<int:event_id>/skip", methods=["POST"])
def events_skip(event_id):
    """Spec L — hide one occurrence of a recurring event (EXDATE)."""
    occ = (request.get_json(silent=True) or {}).get("occurrence")
    if not occ:
        return jsonify({"error": "occurrence is required"}), 400
    return ("", 204) if models.skip_occurrence(event_id, occ) else (jsonify({"error": "not found or not recurring"}), 404)
