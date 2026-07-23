import os

import pytest

from app import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/friday_test"
)


@pytest.fixture
def app():
    # Real Postgres. Empty API key so the LLM is never reached, regardless of the dev's .env.
    app = create_app({"DATABASE_URL": TEST_DB_URL, "TESTING": True,
                      "DEEPSEEK_API_KEY": "", "VOICE_TOKEN": "testsecret"})
    # Fresh state per test: create_app already ran init_db (CREATE IF NOT EXISTS); wipe rows + reset ids.
    with app.app_context():
        from core import db
        conn = db.get_db()
        conn.execute("TRUNCATE settings, events, todos, messages RESTART IDENTITY CASCADE")
        conn.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app):
    """App context for calling model functions directly."""
    with app.app_context():
        yield
