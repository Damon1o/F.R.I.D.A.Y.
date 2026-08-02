"""Files page: the guard that keeps the filesystem API off the cloud deploy, the
read/write round trip, and the local change log."""
import pytest

from app import create_app

FS = {"X-FRIDAY-FS": "1"}


@pytest.fixture()
def fs_client(tmp_path):
    app = create_app({"DESKTOP": True, "ACTIVITY_DB": str(tmp_path / "activity.db")})
    return app.test_client()


def test_filesystem_is_desktop_only():
    web = create_app().test_client()
    assert web.get("/files").status_code == 404
    assert web.get("/api/files?path=C:\\", headers=FS).status_code == 404


def test_api_refuses_calls_without_the_header(fs_client):
    assert fs_client.get("/api/files?path=C:\\").status_code == 403
    assert fs_client.post("/api/files/delete", json={"path": "C:\\"}).status_code == 403


def test_api_refuses_cross_site_calls(fs_client):
    resp = fs_client.get("/api/files?path=C:\\", headers={**FS, "Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403


def test_write_read_rename_and_log(fs_client, tmp_path):
    target = tmp_path / "note.txt"
    written = fs_client.post("/api/files/write", json={"path": str(target), "text": "hello"}, headers=FS)
    assert written.status_code == 200
    assert target.read_text() == "hello"

    read = fs_client.get(f"/api/files/read?path={target}", headers=FS).get_json()
    assert read["text"] == "hello"

    renamed = fs_client.post("/api/files/rename", json={"path": str(target), "name": "kept.txt"},
                             headers=FS).get_json()
    assert renamed["name"] == "kept.txt"
    assert (tmp_path / "kept.txt").exists()

    actions = [r["action"] for r in fs_client.get("/api/activity", headers=FS).get_json()]
    assert actions == ["rename", "create"]      # newest first


def test_listing_a_folder(fs_client, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("x")
    names = [e["name"] for e in fs_client.get(f"/api/files?path={tmp_path}", headers=FS).get_json()["entries"]]
    assert names == ["sub", "a.txt"]            # folders first


def test_delete_goes_to_the_recycle_bin(fs_client, tmp_path):
    doomed = tmp_path / "bye.txt"
    doomed.write_text("x")
    assert fs_client.post("/api/files/delete", json={"path": str(doomed)}, headers=FS).status_code == 200
    assert not doomed.exists()
    assert fs_client.get("/api/activity", headers=FS).get_json()[0]["action"] == "delete"


def test_bad_paths_are_a_400_not_a_500(fs_client, tmp_path):
    assert fs_client.get(f"/api/files?path={tmp_path / 'nope'}", headers=FS).status_code == 400
    assert fs_client.post("/api/files/rename", json={"path": str(tmp_path), "name": "a\\b"},
                          headers=FS).status_code == 400
