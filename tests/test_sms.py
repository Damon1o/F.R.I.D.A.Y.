"""send_sms tool: validation, auth header, error paths. requests always faked."""
import pages.friday.sms as sms
from config import Config
from pages.friday.tools import dispatch


class FakeResp:
    def __init__(self, ok=True, data=None, status_code=200, text=""):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._data = data or {}

    def json(self):
        return self._data


SENT = {"message": {"id": "msg_01HZX", "direction": "outbound"}}


def _fake_key(monkeypatch):
    monkeypatch.setattr(Config, "COMMS_API_KEY", "osis_test", raising=False)


def test_send_sms_posts_with_bearer_and_returns_id(monkeypatch):
    _fake_key(monkeypatch)
    seen = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        seen.update(url=url, body=json, headers=headers)
        return FakeResp(True, SENT)
    monkeypatch.setattr(sms.requests, "post", fake_post)

    assert sms.send_sms("+1 212-555-0147", "hi") == {"sent": True, "id": "msg_01HZX"}
    assert seen["headers"]["Authorization"] == "Bearer osis_test"
    assert seen["body"] == {"to": "+12125550147", "body": "hi"}  # normalised to E.164


def test_send_sms_passes_channel_when_given(monkeypatch):
    _fake_key(monkeypatch)
    seen = {}
    monkeypatch.setattr(sms.requests, "post",
                        lambda url, json=None, **k: (seen.update(json), FakeResp(True, SENT))[1])
    sms.send_sms("+12125550147", "hi", "imessage")
    assert seen["channel"] == "imessage"


def test_send_sms_rejects_bad_number_without_calling_api(monkeypatch):
    _fake_key(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: pytest_fail())
    assert "error" in sms.send_sms("555-0147", "hi")
    assert "error" in sms.send_sms("+12125550147", "   ")


def pytest_fail():
    raise AssertionError("API must not be called for invalid input")


def test_send_sms_without_key_errors(monkeypatch):
    monkeypatch.setattr(Config, "COMMS_API_KEY", "", raising=False)
    assert "not configured" in sms.send_sms("+12125550147", "hi")["error"]


def test_send_sms_http_error_surfaces_status(monkeypatch):
    _fake_key(monkeypatch)
    monkeypatch.setattr(sms.requests, "post",
                        lambda *a, **k: FakeResp(False, status_code=429, text="rate_limited"))
    assert "429" in sms.send_sms("+12125550147", "hi")["error"]


def test_dispatch_send_sms(monkeypatch):
    _fake_key(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: FakeResp(True, SENT))
    assert dispatch("send_sms", {"to": "+12125550147", "body": "hi"})["sent"] is True
