"""Notes: list/view page + /api/notes list, create, delete."""
from flask import Blueprint, jsonify, render_template, request

from pages.notes import models
from pages.notes.models import ValidationError

notes_bp = Blueprint("notes", __name__)


@notes_bp.route("/notes")
def notes_page():
    return render_template("notes.html", notes=models.list_notes())


@notes_bp.route("/api/notes", methods=["GET"])
def notes_list():
    q = request.args.get("q")
    return jsonify(models.search_notes(q) if q else models.list_notes())


@notes_bp.route("/api/notes", methods=["POST"])
def notes_create():
    try:
        return jsonify(models.create_note((request.get_json(silent=True) or {}).get("text"))), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@notes_bp.route("/api/notes/<int:note_id>", methods=["DELETE"])
def notes_delete(note_id):
    return ("", 204) if models.delete_note(note_id) else (jsonify({"error": "not found"}), 404)
