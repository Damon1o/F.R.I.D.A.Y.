"""STT/TTS subprocess wrappers. Real binaries never run — subprocess.run is faked."""
import subprocess
import types

import pytest

from core import stt, tts


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_transcribe_returns_trimmed_stdout(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return FakeProc(stdout="  hello there \n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    text = stt.transcribe("/tmp/in.wav")
    assert text == "hello there"
    assert str(stt.WHISPER_BIN) in seen["argv"]
    assert str(stt.WHISPER_MODEL) in seen["argv"]
    assert "/tmp/in.wav" in seen["argv"]


def test_transcribe_raises_on_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc(returncode=1, stderr="boom"))
    with pytest.raises(stt.STTError):
        stt.transcribe("/tmp/in.wav")


def test_synth_writes_via_piper_and_returns_path(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["input"] = kw.get("input")
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = tts.synth("hello", "/tmp/out.wav")
    assert out == "/tmp/out.wav"
    assert str(tts.PIPER_BIN) in seen["argv"]
    assert str(tts.PIPER_VOICE) in seen["argv"]
    assert "/tmp/out.wav" in seen["argv"]
    assert seen["input"] == "hello"


def test_synth_raises_on_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc(returncode=1, stderr="nope"))
    with pytest.raises(tts.TTSError):
        tts.synth("hi", "/tmp/out.wav")
