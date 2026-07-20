from flask import Flask

from config import Config
from core.db import db


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)

    try:
        from pages.calendar.routes import calendar_bp
        app.register_blueprint(calendar_bp)
    except ImportError:
        pass

    try:
        from pages.chat.routes import chat_bp
        app.register_blueprint(chat_bp)
    except ImportError:
        pass

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)
