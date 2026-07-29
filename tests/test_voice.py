"""Spec B voice: run_text agent helper, STT/TTS wrappers, and the /api/voice endpoint. LLM + binaries always faked."""
import io
import json

from pages.friday import agent, messages


class FakeClient:
    """Returns scripted assistant messages in order (mirrors tests/test_friday.py)."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        return self.scripted.pop(0)


def _tool_call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def test_run_text_runs_tool_then_returns_reply(ctx):
    fake = FakeClient([
        {"role": "assistant", "content": None,
         "tool_calls": [_tool_call("create_todo", {"title": "Buy milk"})]},
        {"role": "assistant", "content": "Added Buy milk to your tasks."},
    ])
    result = agent.run_text("add buy milk", fake)
    assert result["reply"] == "Added Buy milk to your tasks."
    assert result["actions"] == ["create_todo"]
    roles = [m["role"] for m in messages.history()]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_run_text_no_api_key_returns_spoken_error(ctx):
    result = agent.run_text("do something", None)
    assert "DEEPSEEK_API_KEY" in result["reply"]
    assert result["actions"] == []
    assert [m["role"] for m in messages.history()] == ["user"]


# ---- /api/voice endpoint ----

import core.stt as stt_mod          # noqa: E402
import core.tts as tts_mod          # noqa: E402
from pages.voice import routes as voice_routes  # noqa: E402

AUTH = {"Authorization": "Bearer testsecret"}


def _wav_upload(data=b"RIFFfakewav"):
    return {"audio": (io.BytesIO(data), "in.wav")}


def _patch_pipeline(monkeypatch, transcript="add buy milk",
                    reply="Added Buy milk.", actions=("create_todo",)):
    monkeypatch.setattr(voice_routes.stt, "transcribe", lambda p: transcript)
    monkeypatch.setattr(voice_routes.agent, "run_text",
                        lambda text, client=None: {"reply": reply, "actions": list(actions)})

    def fake_synth(text, out_path):
        with open(out_path, "wb") as f:
            f.write(b"RIFFreplywav")
        return out_path

    monkeypatch.setattr(voice_routes.tts, "synth", fake_synth)


def test_voice_requires_token(client):
    res = client.post("/api/voice", data=_wav_upload(), content_type="multipart/form-data")
    assert res.status_code == 401


def test_voice_rejects_wrong_token(client):
    res = client.post("/api/voice", data=_wav_upload(), content_type="multipart/form-data",
                      headers={"Authorization": "Bearer WRONG"})
    assert res.status_code == 401


def test_voice_rejects_missing_audio(client):
    res = client.post("/api/voice", data={}, content_type="multipart/form-data", headers=AUTH)
    assert res.status_code == 400


def test_voice_rejects_oversize_audio(client):
    big = b"x" * (2 * 1024 * 1024 + 1)
    res = client.post("/api/voice", data=_wav_upload(big),
                      content_type="multipart/form-data", headers=AUTH)
    assert res.status_code == 413


def test_voice_happy_path_returns_multipart(client, monkeypatch):
    _patch_pipeline(monkeypatch)
    res = client.post("/api/voice", data=_wav_upload(),
                      content_type="multipart/form-data", headers=AUTH)
    assert res.status_code == 200
    assert res.mimetype == "multipart/mixed"
    body = res.data
    assert b"application/json" in body and b"audio/wav" in body
    assert b"Added Buy milk." in body        # reply text in the JSON part
    assert b"RIFFreplywav" in body           # the synthesized wav bytes


def test_voice_empty_transcript_skips_agent(client, monkeypatch):
    called = {"agent": False}

    def boom(*a, **k):
        called["agent"] = True
        return {"reply": "x", "actions": []}

    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(voice_routes.stt, "transcribe", lambda p: "")
    monkeypatch.setattr(voice_routes.agent, "run_text", boom)
    res = client.post("/api/voice", data=_wav_upload(),
                      content_type="multipart/form-data", headers=AUTH)
    assert res.status_code == 200
    assert called["agent"] is False          # blank STT ⇒ agent not called
    assert b"didn't catch that" in res.data


def test_voice_stt_error_falls_back_to_spoken_reply(client, monkeypatch):
    called = {"agent": False}

    def boom(*a, **k):
        called["agent"] = True
        return {"reply": "x", "actions": []}

    def raise_stt(p):
        raise voice_routes.stt.STTError("whisper exited non-zero")

    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(voice_routes.stt, "transcribe", raise_stt)
    monkeypatch.setattr(voice_routes.agent, "run_text", boom)
    res = client.post("/api/voice", data=_wav_upload(),
                      content_type="multipart/form-data", headers=AUTH)
    assert res.status_code == 200               # STT failure ⇒ spoken 200, not 500
    assert called["agent"] is False             # agent skipped on STT error
    assert b"didn't catch that" in res.data


# ---- /api/voice/stt + /api/voice/tts (browser offline path, no bearer token) ----


def _available(monkeypatch, stt_ok=True, tts_ok=True):
    monkeypatch.setattr(voice_routes.stt, "available", lambda: stt_ok)
    monkeypatch.setattr(voice_routes.tts, "available", lambda: tts_ok)


def test_stt_returns_transcript(client, monkeypatch):
    _available(monkeypatch)
    monkeypatch.setattr(voice_routes.stt, "transcribe", lambda p: "add buy milk")
    res = client.post("/api/voice/stt", data=_wav_upload(), content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["transcript"] == "add buy milk"


def test_stt_error_returns_empty_transcript(client, monkeypatch):
    _available(monkeypatch)

    def raise_stt(p):
        raise voice_routes.stt.STTError("whisper exited non-zero")

    monkeypatch.setattr(voice_routes.stt, "transcribe", raise_stt)
    res = client.post("/api/voice/stt", data=_wav_upload(), content_type="multipart/form-data")
    assert res.status_code == 200                # unrecognizable audio is not an error
    assert res.get_json()["transcript"] == ""


def test_stt_rejects_missing_audio(client, monkeypatch):
    _available(monkeypatch)
    res = client.post("/api/voice/stt", data={}, content_type="multipart/form-data")
    assert res.status_code == 400


def test_stt_rejects_oversize_audio(client, monkeypatch):
    _available(monkeypatch)
    res = client.post("/api/voice/stt", data=_wav_upload(b"x" * (2 * 1024 * 1024 + 1)),
                      content_type="multipart/form-data")
    assert res.status_code == 413


def test_stt_503_when_binary_missing(client, monkeypatch):
    _available(monkeypatch, stt_ok=False)
    res = client.post("/api/voice/stt", data=_wav_upload(), content_type="multipart/form-data")
    assert res.status_code == 503                # client falls back to Web Speech on 503


def test_tts_returns_wav(client, monkeypatch):
    _available(monkeypatch)

    def fake_synth(text, out_path):
        with open(out_path, "wb") as f:
            f.write(b"RIFFyessirwav")
        return out_path

    monkeypatch.setattr(voice_routes.tts, "synth", fake_synth)
    res = client.post("/api/voice/tts", json={"text": "Yes sir."})
    assert res.status_code == 200
    assert res.mimetype == "audio/wav"
    assert res.data == b"RIFFyessirwav"


def test_tts_rejects_empty_text(client, monkeypatch):
    _available(monkeypatch)
    res = client.post("/api/voice/tts", json={"text": "   "})
    assert res.status_code == 400


def test_tts_503_when_binary_missing(client, monkeypatch):
    _available(monkeypatch, tts_ok=False)
    res = client.post("/api/voice/tts", json={"text": "Yes sir."})
    assert res.status_code == 503


def test_tts_503_on_piper_failure(client, monkeypatch):
    _available(monkeypatch)

    def raise_tts(text, out_path):
        raise voice_routes.tts.TTSError("piper exited non-zero")

    monkeypatch.setattr(voice_routes.tts, "synth", raise_tts)
    res = client.post("/api/voice/tts", json={"text": "Yes sir."})
    assert res.status_code == 503


def test_voice_offline_pref_round_trips(client):
    assert client.get("/api/settings/ui").get_json()["voice_offline"] == "false"
    assert client.post("/api/settings/ui", json={"voice_offline": True}).get_json()["voice_offline"] == "true"
    assert client.get("/api/settings/ui").get_json()["voice_offline"] == "true"
