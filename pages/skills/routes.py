"""Skills page: list + plain HTML form posts (no JavaScript, like /notes' server side)."""
from flask import Blueprint, redirect, render_template, request, url_for

from pages.calendar.models import ValidationError
from pages.skills import models

skills_bp = Blueprint("skills", __name__)


@skills_bp.route("/skills")
def skills_page():
    return render_template("skills.html", skills=models.list_skills(), error=request.args.get("error"))


@skills_bp.route("/skills", methods=["POST"])
def skills_create():
    f = request.form
    try:
        models.create_skill(f.get("name"), f.get("trigger"), f.get("body"))
    except ValidationError as e:
        return redirect(url_for("skills.skills_page", error=str(e)))
    return redirect(url_for("skills.skills_page"))


@skills_bp.route("/skills/<int:skill_id>/toggle", methods=["POST"])
def skills_toggle(skill_id):
    skill = models.get_skill(skill_id)
    if skill:
        models.update_skill(skill_id, {"enabled": not skill["enabled"]})
    return redirect(url_for("skills.skills_page"))


@skills_bp.route("/skills/<int:skill_id>/delete", methods=["POST"])
def skills_delete(skill_id):
    models.delete_skill(skill_id)
    return redirect(url_for("skills.skills_page"))
