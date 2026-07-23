"""Settings: static/placeholder page only (no persistence in Phase 1)."""
from flask import Blueprint, render_template

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
def settings_page():
    return render_template("settings.html")
