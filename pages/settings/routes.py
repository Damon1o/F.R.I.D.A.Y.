"""Settings: UI preferences persisted to SQLite."""
from flask import Blueprint, render_template, request, jsonify

from config import Config
from core import reminders
from core.db import query, execute
from pages.friday.sms import E164

settings_bp = Blueprint("settings", __name__)

BOOL_PREFS = {
    "nav_collapsed": "false",
    "friday_visible": "false",
    "wake_word": "false",
    "reminders_sms": "false",
    "clock_24h": "true",
}
# Free-text profile fields. Empty string means "not set".
TEXT_PREFS = {
    "user_name": "",
    "birthday": "",
    "timezone": "",
    "units": "metric",
    "home_lat": "",
    "home_lon": "",
    "home_name": "",
    "reminder_phone": "",
}
DEFAULT_PREFS = {**BOOL_PREFS, **TEXT_PREFS}
_KEYS = tuple(DEFAULT_PREFS)


@settings_bp.route("/settings")
def settings_page():
    prefs = get_prefs()
    return render_template("settings.html", prefs=prefs)


@settings_bp.route("/api/settings/ui", methods=["GET"])
def get_ui_settings():
    return jsonify(get_prefs())


@settings_bp.route("/api/settings/ui", methods=["POST"])
def set_ui_settings():
    data = request.get_json(silent=True) or {}
    for key in BOOL_PREFS:
        if key in data:
            _set_pref(key, "true" if data[key] else "false")
    for key in TEXT_PREFS:
        if key in data:
            value = str(data[key] or "").strip()
            if key == "reminder_phone" and value:
                value = value.replace(" ", "").replace("-", "")
                if not E164.match(value):
                    return jsonify({"error": "phone must be E.164, e.g. +12125550147"}), 400
            if key == "timezone" and value and not _valid_tz(value):
                return jsonify({"error": f"unknown timezone: {value}"}), 400
            if key == "units" and value and value not in ("metric", "imperial"):
                return jsonify({"error": f"unknown units: {value}"}), 400
            _set_pref(key, value)
    return jsonify(get_prefs())


@settings_bp.route("/api/cron/reminders", methods=["GET", "POST"])
def cron_reminders():
    """Day-before reminders. Vercel Cron sends `Authorization: Bearer $CRON_SECRET`.
    No secret configured ⇒ refuse every request (fail closed)."""
    if not Config.CRON_SECRET or request.headers.get("Authorization") != f"Bearer {Config.CRON_SECRET}":
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(reminders.run(force=request.args.get("force") == "1"))


def _valid_tz(name: str) -> bool:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def get_prefs() -> dict:
    """All settings, defaults filled in. Public — the agent reads the profile fields."""
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
