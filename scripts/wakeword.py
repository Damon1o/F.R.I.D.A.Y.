"""Headless "Hey F.R.I.D.A.Y." listener: mic -> wake word -> record -> POST /api/voice -> play reply.

Same openWakeWord models the browser uses (static/vendor/wakeword/), so behaviour matches
static/js/wakeword.js. Run it on any machine with a mic; it talks to a F.R.I.D.A.Y. server.

    pip install onnxruntime sounddevice numpy requests
    python -m scripts.wakeword --url http://localhost:5000 --token $VOICE_TOKEN
"""
import argparse
import io
import os
import time
import wave

import numpy as np
import onnxruntime as ort
import requests
import sounddevice as sd

MODELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "static", "vendor", "wakeword")
RATE = 16000
CHUNK = 1280            # 80 ms — the step size openWakeWord's feature models expect
THRESHOLD = 0.5
SILENCE_RMS = 500       # int16 scale; below this counts as silence
SILENCE_CHUNKS = 15     # ~1.2 s of quiet ends the recording
MAX_RECORD_CHUNKS = 125  # 10 s cap


def _session(name):
    return ort.InferenceSession(os.path.join(MODELS, name + ".onnx"),
                                providers=["CPUExecutionProvider"])


class Detector:
    """Streaming openWakeWord scorer. Feed 1280 samples (int16 scale) at a time."""

    def __init__(self):
        self.mel = _session("melspectrogram")
        self.emb = _session("embedding_model")
        self.ww = _session("hey_friday")
        self.tail = np.zeros(480, dtype=np.float32)   # mel model's 3-frame lookback
        self.mels = np.zeros((0, 32), dtype=np.float32)
        self.feats = np.zeros((0, 96), dtype=np.float32)

    def score(self, chunk: np.ndarray) -> float:
        audio = np.concatenate([self.tail, chunk]).astype(np.float32)
        self.tail = audio[-480:]

        mel = self.mel.run(None, {"input": audio[None, :]})[0].reshape(-1, 32) / 10 + 2
        self.mels = np.vstack([self.mels, mel])[-76:]
        if len(self.mels) < 76:
            return 0.0

        emb = self.emb.run(None, {"input_1": self.mels[None, :, :, None]})[0].reshape(1, 96)
        self.feats = np.vstack([self.feats, emb])[-16:]
        if len(self.feats) < 16:
            return 0.0

        return float(self.ww.run(None, {"embeddings": self.feats[None, :, :]})[0][0][0])

    def reset(self):
        """Drop buffered features so one utterance cannot trigger twice."""
        self.feats = np.zeros((0, 96), dtype=np.float32)


def _wav_bytes(chunks) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.concatenate(chunks).astype(np.int16).tobytes())
    return buf.getvalue()


def _record(stream) -> bytes:
    """Capture until ~1.2 s of silence or the 10 s cap."""
    chunks, quiet = [], 0
    for _ in range(MAX_RECORD_CHUNKS):
        block = stream.read(CHUNK)[0].reshape(-1).astype(np.float32)
        chunks.append(block)
        quiet = quiet + 1 if np.sqrt(np.mean(block ** 2)) < SILENCE_RMS else 0
        if quiet >= SILENCE_CHUNKS and len(chunks) > SILENCE_CHUNKS:
            break
    return _wav_bytes(chunks)


def _play(wav: bytes) -> None:
    with wave.open(io.BytesIO(wav), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        sd.play(data, w.getframerate())
        sd.wait()


def _reply_wav(body: bytes) -> bytes:
    """Pull the audio/wav part out of /api/voice's multipart response."""
    marker = b"Content-Type: audio/wav\r\n\r\n"
    start = body.find(marker)
    if start < 0:
        return b""
    start += len(marker)
    end = body.rfind(b"\r\n--")
    return body[start:end if end > start else len(body)]


def main():
    ap = argparse.ArgumentParser(description='Listen for "Hey Friday" and talk to F.R.I.D.A.Y.')
    ap.add_argument("--url", default=os.environ.get("FRIDAY_URL", "http://localhost:5000"))
    ap.add_argument("--token", default=os.environ.get("VOICE_TOKEN", ""))
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    args = ap.parse_args()

    det = Detector()
    print('Listening for "Hey Friday" — Ctrl+C to stop.')
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        while True:
            chunk = stream.read(CHUNK)[0].reshape(-1).astype(np.float32)
            if det.score(chunk) < args.threshold:
                continue

            print("[wake] listening…")
            det.reset()
            resp = requests.post(
                args.url.rstrip("/") + "/api/voice",
                files={"audio": ("speech.wav", _record(stream), "audio/wav")},
                headers={"Authorization": "Bearer " + args.token},
                timeout=60,
            )
            if resp.status_code != 200:
                print("[error]", resp.status_code, resp.text[:200])
                continue
            wav = _reply_wav(resp.content)
            if wav:
                _play(wav)
            time.sleep(0.5)
            det.tail[:] = 0     # don't score the words we just spoke


if __name__ == "__main__":
    main()
