"""Outbound SMS/iMessage via Comms by Osis. https://docs.osis.co/messages-api/send-message"""
import re

import requests

from config import Config

API_URL = "https://osis.co/api/v1/comms/messages"
E164 = re.compile(r"\+[1-9]\d{6,14}$")


def send_sms(to: str, body: str, channel: str = None) -> dict:
    """Send one message. Returns {"sent": True, "id": ...} or {"error": ...}."""
    if not Config.COMMS_API_KEY:
        return {"error": "messaging is not configured — set COMMS_OSIS_API in .env"}
    to = (to or "").strip().replace(" ", "").replace("-", "")
    if not E164.match(to):
        return {"error": f"'{to}' is not an E.164 phone number (e.g. +12125550147)"}
    if not (body or "").strip():
        return {"error": "message body is empty"}

    payload = {"to": to, "body": body}
    if channel:
        payload["channel"] = channel
    resp = requests.post(API_URL, json=payload, timeout=15,
                         headers={"Authorization": f"Bearer {Config.COMMS_API_KEY}"})
    if not resp.ok:
        return {"error": f"send failed ({resp.status_code}): {resp.text[:200]}"}
    return {"sent": True, "id": resp.json().get("message", {}).get("id")}
