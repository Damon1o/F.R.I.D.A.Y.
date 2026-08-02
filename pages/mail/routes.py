"""Mail OAuth + the one send path. Sending is a human click, never a tool call."""
import secrets

from flask import Blueprint, jsonify, redirect, request

from pages.mail import _settings_get, _settings_put, get_mail

mail_bp = Blueprint("mail", __name__)

STATE_KEY = "gmail_oauth_state"


@mail_bp.route("/mail/connect")
def connect():
    # State lives in `settings`, not the Flask session: the app has no SECRET_KEY,
    # and without a state check the callback is a CSRF endpoint that can attach an
    # attacker's mailbox to this app.
    state = secrets.token_urlsafe(24)
    _settings_put({STATE_KEY: state})
    return redirect(get_mail().auth_url(state))


@mail_bp.route("/mail/callback")
def callback():
    expected = _settings_get((STATE_KEY,)).get(STATE_KEY)
    state = request.args.get("state")
    _settings_put({STATE_KEY: None})            # single use, whatever the outcome
    if not expected or not state or not secrets.compare_digest(state, expected):
        return redirect("/settings?mail_error=state_mismatch")
    code = request.args.get("code")
    if not code or not get_mail().exchange_code(code):
        return redirect("/settings?mail_error=auth_failed")
    return redirect("/settings?mail_connected=1")


@mail_bp.route("/api/mail/status")
def status():
    mail = get_mail()
    return jsonify({"connected": mail.is_connected(), "send_enabled": mail.send_enabled})


@mail_bp.route("/api/mail/send/<draft_id>", methods=["POST"])
def send(draft_id):
    """Sends exactly the named draft. No body text is read, so what the user
    confirmed is what goes out."""
    result = get_mail().send_draft(draft_id)
    return (jsonify(result), 400) if result.get("error") else jsonify(result)
