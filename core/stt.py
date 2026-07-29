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


class STTError(RuntimeError):
    """whisper.cpp failed."""


def available() -> bool:
    """False when the gitignored binary/model are not in vendor/voice (see its README)."""
    return WHISPER_BIN.exists() and WHISPER_MODEL.exists()


def transcribe(wav_path: str) -> str:
    """Return the transcript of a 16 kHz mono 16-bit WAV. Empty string if nothing recognized."""
    proc = subprocess.run(
        [str(WHISPER_BIN), "-m", str(WHISPER_MODEL), "-f", str(wav_path), "-nt", "-np"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise STTError(proc.stderr.strip() or "whisper failed")
    return proc.stdout.strip()
