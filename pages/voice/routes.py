"""Spec B — POST /api/voice: WAV in -> STT -> agent -> TTS -> multipart(JSON, WAV) out."""
import hmac
import json
import os
import tempfile

from flask import Blueprint, Response, current_app, jsonify, request

from core import stt, tts
from pages.friday import agent

voice_bp = Blueprint("voice", __name__)

MAX_AUDIO_BYTES = 2 * 1024 * 1024          # ~60s of 16 kHz mono 16-bit
_BOUNDARY = "friday-voice-boundary"
_EMPTY_STT_REPLY = "I didn't catch that."


def _authorized() -> bool:
    token = current_app.config.get("VOICE_TOKEN") or ""
    if not token:
        return False                       # fail closed: unconfigured ⇒ deny
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    sent = header[len(prefix):] if header.startswith(prefix) else ""
    return bool(sent) and hmac.compare_digest(sent, token)


def _multipart(meta: dict, wav_bytes: bytes) -> Response:
    b = _BOUNDARY
    parts = (
        f"--{b}\r\nContent-Type: application/json\r\n\r\n"
        f"{json.dumps(meta)}\r\n"
        f"--{b}\r\nContent-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + wav_bytes + f"\r\n--{b}--\r\n".encode("utf-8")
    return Response(parts, mimetype=f"multipart/mixed; boundary={b}")


@voice_bp.route("/api/voice", methods=["POST"])
def voice():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    upload = request.files.get("audio")
    if upload is None:
        return jsonify({"error": "no audio"}), 400
    audio = upload.read()
    if not audio:
        return jsonify({"error": "no audio"}), 400
    if len(audio) > MAX_AUDIO_BYTES:
        return jsonify({"error": "audio too large"}), 413

    in_fd, in_path = tempfile.mkstemp(suffix=".wav")
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)
    try:
        with os.fdopen(in_fd, "wb") as f:
            f.write(audio)

        try:
            transcript = stt.transcribe(in_path)
        except stt.STTError:
            transcript = ""            # unrecognizable audio ⇒ spoken fallback (spec §5)
        if transcript:
            result = agent.run_text(transcript)
            reply, actions = result["reply"], result["actions"]
        else:
            reply, actions = _EMPTY_STT_REPLY, []

        tts.synth(reply, out_path)
        with open(out_path, "rb") as f:
            wav_bytes = f.read()

        return _multipart({"transcript": transcript, "reply": reply, "actions": actions}, wav_bytes)
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


# ---- Browser-side offline voice (same-origin, no bearer token) ----
# The browser cannot hold the VOICE_TOKEN secret, and the rest of the app is unauthenticated
# anyway. These two split /api/voice's pipeline so the existing chat path stays in the middle:
# the page transcribes here, submits the normal chat form, then speaks the reply here.
# 503 (not 500) when the vendor binaries are missing, so the client can fall back to Web Speech.


@voice_bp.route("/api/voice/stt", methods=["POST"])
def voice_stt():
    if not stt.available():
        return jsonify({"error": "stt unavailable"}), 503

    upload = request.files.get("audio")
    audio = upload.read() if upload is not None else b""
    if not audio:
        return jsonify({"error": "no audio"}), 400
    if len(audio) > MAX_AUDIO_BYTES:
        return jsonify({"error": "audio too large"}), 413

    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        try:
            transcript = stt.transcribe(path)
        except stt.STTError:
            transcript = ""            # unrecognizable audio ⇒ empty, same as /api/voice
        return jsonify({"transcript": transcript})
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@voice_bp.route("/api/voice/tts", methods=["POST"])
def voice_tts():
    if not tts.available():
        return jsonify({"error": "tts unavailable"}), 503

    text = (request.get_json(silent=True) or {}).get("text", "")
    text = str(text).strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        try:
            tts.synth(text, path)
        except tts.TTSError:
            return jsonify({"error": "tts failed"}), 503
        with open(path, "rb") as f:
            return Response(f.read(), mimetype="audio/wav")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
