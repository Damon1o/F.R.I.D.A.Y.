"""Speech-to-text via a bundled whisper.cpp binary. No Python bindings (stdlib subprocess)."""
import subprocess
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "voice"


def _bin(name: str) -> Path:
    """Windows dev builds are `<name>.exe`; the Vercel Linux build has no suffix."""
    exe = VENDOR / f"{name}.exe"
    return exe if exe.exists() else VENDOR / name


WHISPER_BIN = _bin("whisper-cli")
WHISPER_MODEL = VENDOR / "ggml-tiny.en.bin"
# Clips are capped at ~10 s; anything past this is a wedged binary holding a request thread.
TIMEOUT = 60


class STTError(RuntimeError):
    """whisper.cpp failed."""


def available() -> bool:
    """False when the gitignored binary/model are not in vendor/voice (see its README)."""
    return WHISPER_BIN.exists() and WHISPER_MODEL.exists()


def transcribe(wav_path: str) -> str:
    """Return the transcript of a 16 kHz mono 16-bit WAV. Empty string if nothing recognized."""
    try:
        proc = subprocess.run(
            [str(WHISPER_BIN), "-m", str(WHISPER_MODEL), "-f", str(wav_path), "-nt", "-np"],
            capture_output=True, text=True,
            # whisper-cli is a console app: without this Windows flashes a terminal per utterance.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise STTError("whisper timed out")
    if proc.returncode != 0:
        raise STTError(proc.stderr.strip() or "whisper failed")
    return proc.stdout.strip()
