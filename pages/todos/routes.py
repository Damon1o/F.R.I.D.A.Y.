"""To-Do: list page + /api/todos CRUD."""
from flask import Blueprint, jsonify, render_template, request

from pages.calendar.models import ValidationError
from pages.todos import models

todos_bp = Blueprint("todos", __name__)


@todos_bp.route("/todos")
def todos_page():
    return render_template("todos.html", todos=models.list_todos())


@todos_bp.route("/api/todos", methods=["GET"])
def todos_list():
    done = request.args.get("done")
    done = None if done is None else done == "1"
    return jsonify(models.list_todos(done=done))


@todos_bp.route("/api/todos", methods=["POST"])
def todos_create():
    try:
        return jsonify(models.create_todo(request.get_json(silent=True) or {})), 201
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400


@todos_bp.route("/api/todos/<int:todo_id>", methods=["PATCH"])
def todos_update(todo_id):
    try:
        todo = models.update_todo(todo_id, request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return (jsonify(todo), 200) if todo else (jsonify({"error": "not found"}), 404)


@todos_bp.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def todos_delete(todo_id):
    return ("", 204) if models.delete_todo(todo_id) else (jsonify({"error": "not found"}), 404)
