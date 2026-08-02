"""Files page (browse + edit anywhere on the machine) and the local Activity log.

Desktop-only, and deliberately paranoid about who is calling: the server listens on
localhost, so any page open in any browser could otherwise POST to it. Two cheap locks:

* every API call must carry `X-FRIDAY-FS` — a custom header forces a CORS preflight that
  a cross-origin page cannot satisfy, and a plain HTML form cannot send one at all;
* `Sec-Fetch-Site` must say same-origin.
"""
from flask import Blueprint, current_app, jsonify, render_template, request

from pages.files import models
from pages.files.models import FileError

files_bp = Blueprint("files", __name__)


def _desktop_only():
    """The Vercel deploy must never expose the filesystem — 404, not 403: the route
    simply does not exist off the desktop build."""
    if not current_app.config.get("DESKTOP"):
        return jsonify({"error": "not found"}), 404
    return None


def _guarded():
    blocked = _desktop_only()
    if blocked:
        return blocked
    if request.headers.get("X-FRIDAY-FS") != "1":
        return jsonify({"error": "forbidden"}), 403
    if request.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
        return jsonify({"error": "forbidden"}), 403
    return None


def _body() -> dict:
    return request.get_json(silent=True) or {}


@files_bp.route("/files")
def files_page():
    if not current_app.config.get("DESKTOP"):
        return "Not found", 404
    return render_template("files.html", roots=models.roots())


@files_bp.route("/activity")
def activity_page():
    if not current_app.config.get("DESKTOP"):
        return "Not found", 404
    return render_template("activity.html", rows=models.entries())


@files_bp.route("/api/files")
def files_list():
    blocked = _guarded()
    if blocked:
        return blocked
    path = request.args.get("path", "")
    try:
        return jsonify(models.listdir(path) if path else
                       {"path": "", "parent": "", "entries": models.roots()})
    except FileError as e:
        return jsonify({"error": str(e)}), 400


@files_bp.route("/api/files/read")
def files_read():
    blocked = _guarded()
    if blocked:
        return blocked
    try:
        return jsonify(models.read_text(request.args.get("path", "")))
    except FileError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        return jsonify({"error": str(e)}), 400


@files_bp.route("/api/files/search")
def files_search():
    blocked = _guarded()
    if blocked:
        return blocked
    try:
        return jsonify(models.search(request.args.get("path", ""), request.args.get("q", "")))
    except FileError as e:
        return jsonify({"error": str(e)}), 400


# One handler per verb rather than a switch: each takes different arguments, and a
# generic "action" endpoint is exactly the shape you regret when it grows.
@files_bp.route("/api/files/write", methods=["POST"])
def files_write():
    return _do(lambda b: models.write_text(b.get("path", ""), b.get("text", "")))


@files_bp.route("/api/files/mkdir", methods=["POST"])
def files_mkdir():
    return _do(lambda b: models.mkdir(b.get("path", "")))


@files_bp.route("/api/files/rename", methods=["POST"])
def files_rename():
    return _do(lambda b: models.rename(b.get("path", ""), b.get("name", "")))


@files_bp.route("/api/files/move", methods=["POST"])
def files_move():
    return _do(lambda b: models.move(b.get("path", ""), b.get("to", "")))


@files_bp.route("/api/files/delete", methods=["POST"])
def files_delete():
    return _do(lambda b: models.delete(b.get("path", "")) or {"ok": True})


@files_bp.route("/api/activity")
def activity_list():
    blocked = _guarded()
    if blocked:
        return blocked
    return jsonify(models.entries(request.args.get("limit", type=int) or 200))


def _do(fn):
    blocked = _guarded()
    if blocked:
        return blocked
    try:
        return jsonify(fn(_body()))
    except FileError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:                      # permission denied, file in use, bad name
        return jsonify({"error": str(e)}), 400
