import pytest

from app import create_app
from core.db import db


@pytest.fixture
def app():
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with application.app_context():
        yield application
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
