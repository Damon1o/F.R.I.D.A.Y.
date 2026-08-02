"""Spec M — Gmail. Reading and drafting are free; sending is not reachable from the tool loop.

The send path lives behind POST /api/mail/send/<draft_id>, which a human clicks. No
`send_email` tool exists on purpose (see tests/test_mail.py), so no sequence of model
outputs can put mail on the wire.
"""
import base64
import os
import re
from email.message import EmailMessage
from urllib.parse import urlencode

import requests

API = "https://www.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
BODY_CHARS = 4000        # a full inbox in the prompt is cost and injection surface
NOT_CONNECTED = {"error": "email not connected — connect Gmail in settings"}

# gmail.send is requested only when the user turns sending on; a deployment that
# never does cannot send mail even if every other layer fails.
READ_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
               "https://www.googleapis.com/auth/gmail.compose"]
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _settings_get(keys):
    try:
        from core.db import query
        return {r["key"]: r["value"] for r in query(
            "SELECT key, value FROM settings WHERE key = ANY(%s)", (list(keys),))}
    except Exception:
        return {}


def _settings_put(pairs):
    try:
        from core.db import execute
        for key, val in pairs.items():
            if val is None:
                execute("DELETE FROM settings WHERE key = %s", (key,))
                continue
            execute("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
                    (key, val))
    except Exception:
        pass


class GmailProvider:
    def __init__(self):
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = os.environ.get(
            "GOOGLE_REDIRECT_URI", "http://localhost:5000/mail/callback")
        stored = _settings_get(("gmail_access_token", "gmail_refresh_token", "gmail_send_enabled"))
        self._access = stored.get("gmail_access_token") or os.environ.get("GMAIL_ACCESS_TOKEN")
        self._refresh = stored.get("gmail_refresh_token") or os.environ.get("GMAIL_REFRESH_TOKEN")
        self.send_enabled = stored.get("gmail_send_enabled") == "true"

    # ---- auth ----

    def is_connected(self) -> bool:
        return bool(self._access or self._refresh)

    def auth_url(self, state: str) -> str:
        scopes = READ_SCOPES + ([SEND_SCOPE] if self.send_enabled else [])
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id or "", "redirect_uri": self.redirect_uri,
            "response_type": "code", "scope": " ".join(scopes), "state": state,
            "access_type": "offline", "prompt": "consent",
        })

    def exchange_code(self, code: str) -> bool:
        if not self.client_id or not self.client_secret:
            return False
        resp = requests.post(TOKEN_URL, timeout=10, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id, "client_secret": self.client_secret})
        if not resp.ok:
            return False
        data = resp.json()
        self._access = data.get("access_token")
        self._refresh = data.get("refresh_token") or self._refresh
        _settings_put({"gmail_access_token": self._access, "gmail_refresh_token": self._refresh})
        return True

    def _refresh_access(self) -> bool:
        if not (self._refresh and self.client_id and self.client_secret):
            return False
        resp = requests.post(TOKEN_URL, timeout=10, data={
            "grant_type": "refresh_token", "refresh_token": self._refresh,
            "client_id": self.client_id, "client_secret": self.client_secret})
        if not resp.ok:
            return False
        data = resp.json()
        self._access = data.get("access_token")
        self._refresh = data.get("refresh_token") or self._refresh
        _settings_put({"gmail_access_token": self._access, "gmail_refresh_token": self._refresh})
        return True

    def _request(self, method: str, path: str, **kw):
        if not self.is_connected():
            return None
        headers = {"Authorization": f"Bearer {self._access}"}
        resp = requests.request(method, API + path, headers=headers, timeout=10, **kw)
        if resp.status_code == 401 and self._refresh_access():
            headers["Authorization"] = f"Bearer {self._access}"
            resp = requests.request(method, API + path, headers=headers, timeout=10, **kw)
        return resp if resp.ok else None

    # ---- reading ----

    def list_unread(self, count: int = 10):
        return self._listing("is:unread", count)

    def search(self, query: str, count: int = 10):
        return self._listing(query, count)

    def _listing(self, q: str, count: int):
        if not self.is_connected():
            return NOT_CONNECTED
        count = max(1, min(int(count), 20))
        resp = self._request("GET", "/messages", params={"q": q, "maxResults": count})
        if resp is None:
            return {"error": "email request failed — reconnect Gmail in settings"}
        out = []
        for stub in (resp.json().get("messages") or [])[:count]:
            meta = self._request("GET", f"/messages/{stub['id']}",
                                 params={"format": "metadata",
                                         "metadataHeaders": ["From", "Subject", "Date"]})
            if meta is not None:
                out.append(_summary(meta.json()))
        return out

    def read_message(self, message_id: str):
        if not self.is_connected():
            return NOT_CONNECTED
        resp = self._request("GET", f"/messages/{message_id}", params={"format": "full"})
        if resp is None:
            return {"error": "message not found"}
        data = resp.json()
        out = _summary(data)
        out["body"] = _body(data.get("payload") or {})[:BODY_CHARS]
        return out

    # ---- drafting (never sending) ----

    def create_draft(self, to: str, subject: str, body: str, thread_id=None):
        if not self.is_connected():
            return NOT_CONNECTED
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        payload = {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        resp = self._request("POST", "/drafts", json=payload)
        if resp is None:
            return {"error": "could not create the draft"}
        return {"draft_id": resp.json().get("id"), "to": to, "subject": subject,
                "preview": body[:500]}

    def send_draft(self, draft_id: str):
        """Only the confirm route calls this. It takes a draft id and no text, so the
        message the user read is byte-identical to the message that goes out."""
        if not self.send_enabled:
            return {"error": "sending is disabled — enable it in settings and reconnect"}
        resp = self._request("POST", "/drafts/send", json={"id": draft_id})
        if resp is None:
            return {"error": "send failed"}
        return {"sent": True, "message_id": resp.json().get("id")}


def _header(msg, name, default=""):
    for h in (msg.get("payload") or {}).get("headers") or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", default)
    return default


def _summary(msg) -> dict:
    """Redaction is part of the return shape: routing metadata never enters the prompt."""
    return {"id": msg.get("id"), "thread_id": msg.get("threadId"),
            "from": _header(msg, "From"), "subject": _header(msg, "Subject"),
            "date": _header(msg, "Date"), "snippet": msg.get("snippet", "")}


def _decode(part) -> str:
    raw = (part.get("body") or {}).get("data")
    if not raw:
        return ""
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")


def _body(payload) -> str:
    """Prefer text/plain; fall back to stripping tags off the HTML alternative."""
    if payload.get("mimeType") == "text/plain":
        return _decode(payload)
    for part in payload.get("parts") or []:
        text = _body(part)
        if text and part.get("mimeType") == "text/plain":
            return text
    for part in payload.get("parts") or []:
        if part.get("mimeType") == "text/html":
            return _strip_html(_decode(part))
        nested = _body(part)
        if nested:
            return nested
    if payload.get("mimeType") == "text/html":
        return _strip_html(_decode(payload))
    return _decode(payload)


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def get_mail() -> GmailProvider:
    return GmailProvider()
