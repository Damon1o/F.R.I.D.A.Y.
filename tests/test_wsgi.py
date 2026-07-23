import tests.conftest as ct


def test_wsgi_entrypoint_exposes_flask_app(monkeypatch):
    # api/index.py calls create_app() with no overrides, so it reads DATABASE_URL from env.
    monkeypatch.setenv("DATABASE_URL", ct.TEST_DB_URL)
    from api.index import app
    assert callable(app.wsgi_app)          # it's a Flask/WSGI app
    assert "friday" in app.blueprints      # our blueprints are registered
