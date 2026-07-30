"""F.R.I.D.A.Y. — Flask app factory. Server-rendered Jinja + Postgres via psycopg, no build step."""
import re
import uuid
from functools import lru_cache
from pathlib import Path

from flask import Flask, g, request
from markupsafe import Markup

from config import Config
from core import db

LUCIDE_DIR = Path(__file__).resolve().parent / "static" / "vendor" / "lucide"
LOGO_PATH = Path(__file__).resolve().parent / "static" / "images" / "friday.svg"
SESSION_COOKIE = "friday_session"


@lru_cache(maxsize=64)
def _load_icon(name: str) -> str:
    svg = (LUCIDE_DIR / f"{name}.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)  # drop license comment
    return svg.strip()


def render_icon(name: str, size: int = 20, cls: str = "") -> Markup:
    """Inline a self-hosted Lucide SVG. Icons only, never emoji."""
    svg = _load_icon(name)
    svg = re.sub(r'\bwidth="24"', f'width="{size}"', svg, count=1)
    svg = re.sub(r'\bheight="24"', f'height="{size}"', svg, count=1)
    new_cls = ("icon " + cls).strip()
    if 'class="' in svg:
        svg = re.sub(r'class="[^"]*"', f'class="{new_cls}"', svg, count=1)
    else:
        svg = svg.replace("<svg", f'<svg class="{new_cls}"', 1)
    return Markup(svg)


def render_logo(cls: str = "") -> Markup:
    """Inline F.R.I.D.A.Y. logo SVG so it inherits color from parent."""
    raw = LOGO_PATH.read_text(encoding="utf-8")
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    raw = re.sub(r"<\?xml.*?\?>", "", raw, count=1)
    raw = re.sub(r"<!DOCTYPE.*?>", "", raw, count=1, flags=re.S)
    raw = raw.strip()
    new_cls = ("brand-logo " + cls).strip() if cls else "brand-logo"
    raw = re.sub(r'class="([^"]*)"', f'class="{new_cls} \\1"', raw, count=1) if 'class="' in raw else raw.replace("<svg", f'<svg class="{new_cls}"', 1)
    return Markup(raw)


def _get_session_id() -> str:
    """Return or create a session_id for this request (stored in cookie)."""
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = uuid.uuid4().hex[:16]
    g.session_id = sid
    return sid


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
    with app.app_context():
        db.init_db()
    app.jinja_env.globals["icon"] = render_icon
    app.jinja_env.globals["logo"] = render_logo

    @app.before_request
    def _ensure_session():
        _get_session_id()

    @app.before_request
    def _load_ui_prefs():
        from core.db import query
        row = query("SELECT value FROM settings WHERE key = 'friday_visible'", one=True)
        g.friday_visible = row["value"] if row else "false"

    @app.context_processor
    def _inject_ui_prefs():
        return {"friday_visible": getattr(g, "friday_visible", "false")}

    @app.after_request
    def _set_session_cookie(resp):
        if hasattr(g, "session_id"):
            resp.set_cookie(SESSION_COOKIE, g.session_id, max_age=31536000, httponly=True, samesite="Lax")
        return resp

    from pages.dashboard.routes import dashboard_bp
    from pages.calendar.routes import calendar_bp
    from pages.todos.routes import todos_bp
    from pages.settings.routes import settings_bp
    from pages.friday.routes import friday_bp
    from pages.voice.routes import voice_bp
    from pages.music.routes import music_bp
    from pages.notes.routes import notes_bp
    from pages.search.routes import search_bp
    from pages.grades.routes import grades_bp
    from pages.sat.routes import sat_bp

    for bp in (dashboard_bp, calendar_bp, todos_bp, settings_bp, friday_bp, voice_bp, music_bp, notes_bp, search_bp,
               grades_bp, sat_bp):
        app.register_blueprint(bp)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host=Config.HOST, port=Config.PORT, debug=True)
