"""Notes: list/view page + /api/notes list, create, delete."""
from flask import Blueprint, jsonify, render_template, request

from pages.notes import models
from pages.notes.models import ValidationError

notes_bp = Blueprint("notes", __name__)


PAGE = 30  # first screenful; the rest streams in as the list is scrolled


@notes_bp.route("/notes")
def notes_page():
    total = models.count_notes()
    return render_template(
        "notes.html", notes=models.list_notes(limit=PAGE), total=total, page_size=PAGE,
    )


@notes_bp.route("/api/notes", methods=["GET"])
def notes_list():
    q = request.args.get("q")
    if q:
        return jsonify(models.search_notes(q))
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int) or 0
    return jsonify(models.list_notes(limit=limit, offset=offset))


@notes_bp.route("/api/notes", methods=["POST"])
def notes_create():
    try:
        return jsonify(models.create_note((request.get_json(silent=True) or {}).get("text"))), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@notes_bp.route("/api/notes/<int:note_id>", methods=["DELETE"])
def notes_delete(note_id):
    return ("", 204) if models.delete_note(note_id) else (jsonify({"error": "not found"}), 404)
