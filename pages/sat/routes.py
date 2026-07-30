"""SAT Prep — stub. Its own spec covers score-report ingest and question generation."""
from flask import Blueprint, render_template

sat_bp = Blueprint("sat", __name__)


@sat_bp.route("/sat")
def sat_page():
    return render_template("sat.html")
