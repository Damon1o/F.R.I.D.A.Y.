"""Settings: UI preferences persisted to SQLite."""
from flask import Blueprint, render_template, request, jsonify

from core.db import query, execute

settings_bp = Blueprint("settings", __name__)

DEFAULT_PREFS = {
    "nav_collapsed": "false",
    "friday_visible": "true",
    "wake_word": "false",
}
_KEYS = tuple(DEFAULT_PREFS)


@settings_bp.route("/settings")
def settings_page():
    prefs = _get_prefs()
    return render_template("settings.html", prefs=prefs)


@settings_bp.route("/api/settings/ui", methods=["GET"])
def get_ui_settings():
    return jsonify(_get_prefs())


@settings_bp.route("/api/settings/ui", methods=["POST"])
def set_ui_settings():
    data = request.get_json(silent=True) or {}
    for key in _KEYS:
        if key in data:
            _set_pref(key, "true" if data[key] else "false")
    return jsonify(_get_prefs())


def _get_prefs() -> dict:
    placeholders = ", ".join(["%s"] * len(_KEYS))
    rows = query(f"SELECT key, value FROM settings WHERE key IN ({placeholders})", _KEYS)
    prefs = DEFAULT_PREFS.copy()
    for row in rows:
        prefs[row["key"]] = row["value"]
    return prefs


def _set_pref(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
        (key, value),
    )
