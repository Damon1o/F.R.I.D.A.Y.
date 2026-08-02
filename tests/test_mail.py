"""Spec M — Gmail. The load-bearing test is that `send_email` does not exist."""
import base64
import json

import pytest

from pages import mail
from pages.friday import agent
from pages.friday.tools import TOOLS, dispatch


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


MESSAGE = {
    "id": "m1", "threadId": "t1", "snippet": "running late",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "From", "value": "Kate <kate@example.com>"},
                    {"name": "Subject", "value": "Lunch"},
                    {"name": "Date", "value": "Sat, 1 Aug 2026 12:00:00 -0400"},
                    {"name": "Received", "value": "from mx.example.com by ..."}],
        "parts": [{"mimeType": "text/plain", "body": {"data": _b64("running late, start without me")}}],
    },
}


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.ok = status < 400
        self.content = b"x"

    def json(self):
        return self.payload


@pytest.fixture
def gmail(app, monkeypatch):
    """A connected provider whose HTTP layer is scripted per (method, path)."""
    calls = []

    def fake_request(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        path = url.split("/users/me", 1)[1]
        if path.startswith("/messages/"):
            return FakeResp(MESSAGE)
        if path.startswith("/messages"):
            return FakeResp({"messages": [{"id": "m1", "threadId": "t1"}]})
        if path == "/drafts":
            return FakeResp({"id": "d1"})
        if path == "/drafts/send":
            return FakeResp({"id": "sent1"})
        return FakeResp({}, 404)

    monkeypatch.setattr(mail.requests, "request", fake_request)
    monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    with app.app_context():
        yield calls


# ---- the design's main guarantee ----

def test_send_email_is_not_a_tool(ctx):
    assert "send_email" not in [t["function"]["name"] for t in TOOLS]
    assert dispatch("send_email", {"to": "a@b.c", "body": "hi"}) == \
        {"error": "unknown tool send_email"}


# ---- reading ----

def test_listing_is_redacted_to_the_summary_shape(gmail):
    rows = mail.get_mail().list_unread(5)
    assert rows == [{"id": "m1", "thread_id": "t1", "from": "Kate <kate@example.com>",
                     "subject": "Lunch", "date": "Sat, 1 Aug 2026 12:00:00 -0400",
                     "snippet": "running late"}]
    assert "Received" not in json.dumps(rows)   # routing metadata never enters the prompt


def test_read_message_returns_plain_body(gmail):
    assert mail.get_mail().read_message("m1")["body"] == "running late, start without me"


def test_html_only_body_is_stripped_to_text():
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html",
         "body": {"data": _b64("<style>p{}</style><p>Hello <b>there</b></p>")}}]}
    assert mail._body(payload) == "Hello there"


def test_body_truncates(gmail, monkeypatch):
    long = {**MESSAGE, "payload": {**MESSAGE["payload"], "parts": [
        {"mimeType": "text/plain", "body": {"data": _b64("z" * 9000)}}]}}
    monkeypatch.setattr(mail.requests, "request", lambda *a, **k: FakeResp(long))
    assert len(mail.get_mail().read_message("m1")["body"]) == mail.BODY_CHARS


# ---- drafting and the send gate ----

def test_draft_returns_an_id_and_preview(gmail):
    d = dispatch("draft_email", {"to": "kate@example.com", "subject": "Late",
                                 "body": "on my way"})
    assert d == {"draft_id": "d1", "to": "kate@example.com", "subject": "Late",
                 "preview": "on my way"}


def test_send_route_sends_that_draft_and_ignores_posted_text(client, gmail, monkeypatch):
    mail._settings_put({"gmail_send_enabled": "true"})
    res = client.post("/api/mail/send/d1", json={"body": "attacker text"})
    assert res.get_json() == {"sent": True, "message_id": "sent1"}
    sent = [c for c in gmail if c["url"].endswith("/drafts/send")]
    assert sent[0]["json"] == {"id": "d1"}          # id only; no body text reaches Gmail


def test_send_is_refused_while_disabled(client, gmail):
    assert client.post("/api/mail/send/d1").status_code == 400


# ---- auth ----

def test_callback_rejects_a_mismatched_state(client, gmail):
    mail._settings_put({"gmail_oauth_state": "expected"})
    res = client.get("/mail/callback?code=abc&state=forged")
    assert "state_mismatch" in res.headers["Location"]


def test_state_is_single_use(client, gmail):
    mail._settings_put({"gmail_oauth_state": "expected"})
    client.get("/mail/callback?code=abc&state=expected")
    res = client.get("/mail/callback?code=abc&state=expected")
    assert "state_mismatch" in res.headers["Location"]


def test_refresh_on_401_retries_once_and_persists_tokens(app, monkeypatch):
    seen = {"gets": 0}

    def fake_request(method, url, **kw):
        seen["gets"] += 1
        return FakeResp({"messages": []}, 401 if seen["gets"] == 1 else 200)

    monkeypatch.setattr(mail.requests, "request", fake_request)
    monkeypatch.setattr(mail.requests, "post",
                        lambda *a, **k: FakeResp({"access_token": "fresh"}))
    monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "stale")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "r1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    with app.app_context():
        mail.get_mail().list_unread(1)
        assert seen["gets"] == 2
        assert mail._settings_get(("gmail_access_token",))["gmail_access_token"] == "fresh"


# ---- not connected ----

def test_every_tool_errors_politely_when_not_connected(ctx, monkeypatch):
    for var in ("GMAIL_ACCESS_TOKEN", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    for name, args in (("list_unread", {}), ("search_mail", {"query": "x"}),
                       ("read_message", {"message_id": "m1"}),
                       ("draft_email", {"to": "a@b.c", "subject": "s", "body": "b"})):
        assert "error" in dispatch(name, args)


# ---- injection ----

def test_a_draft_emits_a_confirm_frame_and_never_sends(ctx, gmail, monkeypatch):
    """The stream offers a button; nothing leaves without the click."""
    class Fake:
        def __init__(self):
            self.scripted = [
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "c1", "type": "function", "function": {
                        "name": "draft_email",
                        "arguments": json.dumps({"to": "kate@example.com",
                                                 "subject": "Late", "body": "on my way"})}}]},
                {"role": "assistant", "content": "Drafted it."},
            ]

        def complete(self, messages, tools=None):
            return self.scripted.pop(0) if self.scripted else \
                {"role": "assistant", "content": "Title"}

    frames = list(agent.run_turn("email kate", Fake()))
    actions = [p for e, p in frames if e == "action"]
    assert actions and actions[0]["type"] == "confirm_send" and actions[0]["draft_id"] == "d1"
    assert not [c for c in gmail if c["url"].endswith("/drafts/send")]
