import os

import pytest

from app import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/friday_test"
)

# The app fixture TRUNCATEs every table. If TEST_DATABASE_URL ever points at the
# real database, a test run silently destroys real data -- refuse to start.
if TEST_DB_URL == os.environ.get("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL equals DATABASE_URL; tests would wipe real data")


@pytest.fixture
def app():
    # Real Postgres. Empty API key so the LLM is never reached, regardless of the dev's .env.
    app = create_app({"DATABASE_URL": TEST_DB_URL, "TESTING": True,
                      "DEEPSEEK_API_KEY": "", "VOICE_TOKEN": "testsecret"})
    # create_app no longer inits the DB; do it here. Ensure schema (CREATE IF
    # NOT EXISTS), then wipe rows + reset ids for fresh state per test.
    with app.app_context():
        from core import db
        db.init_db()
        conn = db.get_db()
        conn.execute("TRUNCATE settings, events, todos, notes, messages, undo_log RESTART IDENTITY CASCADE")
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
