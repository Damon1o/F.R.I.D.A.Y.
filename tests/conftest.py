import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    # File-backed temp DB (not :memory:, which wouldn't survive per-request connections).
    return create_app({"DB_PATH": str(tmp_path / "test.db"), "TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app):
    """App context for calling model functions directly."""
    with app.app_context():
        yield
