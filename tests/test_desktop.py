"""Desktop build: the two bits that are not just packaging — the offline page and the
update-check version compare."""
import pytest

from app import create_app
from desktop.update import _newer

DEAD_DB = "postgresql://x:y@127.0.0.1:59999/nope"


def test_unreachable_db_renders_offline_page():
    app = create_app({"DATABASE_URL": DEAD_DB})
    resp = app.test_client().get("/")
    assert resp.status_code == 503
    assert b"No connection" in resp.data


@pytest.mark.parametrize("tag, newer", [
    ("v9.0.0", True), ("1.0.1", True), ("1.0.0", False), ("v0.9.9", False), ("nightly", False),
])
def test_update_version_compare(tag, newer):
    assert _newer(tag) is newer
