"""SAT Prep: /sat page, question generation, grading, the full test, and stats."""
from flask import Blueprint, jsonify, render_template, request

from pages.sat import models

sat_bp = Blueprint("sat", __name__)


@sat_bp.route("/sat")
def sat_page():
    return render_template("sat.html", taxonomy=models.TAXONOMY,
                           progress=models.progress(),
                           difficulties=models.DIFFICULTIES,
                           tests=models.tests(),
                           chart=models.chart(),
                           open_test=models.open_test(),
                           modules=models.MODULES)


@sat_bp.route("/api/sat/generate", methods=["POST"])
def sat_generate():
    body = request.get_json(silent=True) or {}
    result = models.generate(body.get("section", ""), body.get("skill") or None,
                             body.get("difficulty", "medium"), body.get("count", 4))
    return jsonify(result), (200 if not result["error"] else 400)


@sat_bp.route("/api/sat/answer", methods=["POST"])
def sat_answer():
    body = request.get_json(silent=True) or {}
    result = models.answer(body.get("question_id"), body.get("chosen", ""))
    return jsonify(result), (200 if not result.get("error") else 400)


@sat_bp.route("/api/sat/progress", methods=["GET"])
def sat_progress():
    return jsonify(models.progress())


@sat_bp.route("/api/sat/reset", methods=["POST"])
def sat_reset():
    return jsonify(models.reset())


# ---- Full-length test ---- #
@sat_bp.route("/api/sat/test", methods=["POST"])
def sat_test_start():
    result = models.start_test()
    return jsonify(result), (200 if not result["error"] else 400)


@sat_bp.route("/api/sat/test/<int:test_id>/module/<module>", methods=["POST"])
def sat_test_module(test_id, module):
    result = models.build_module(test_id, module)
    return jsonify(result), (200 if not result["error"] else 400)


@sat_bp.route("/api/sat/test/answer", methods=["POST"])
def sat_test_answer():
    body = request.get_json(silent=True) or {}
    result = models.answer_item(body.get("item_id"), body.get("chosen", ""))
    return jsonify(result), (200 if not result.get("error") else 400)


@sat_bp.route("/api/sat/test/<int:test_id>/finish", methods=["POST"])
def sat_test_finish(test_id):
    return jsonify(models.finish_test(test_id))
