"""Speech-to-text via a bundled whisper.cpp binary. No Python bindings (stdlib subprocess)."""
import subprocess
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "voice"
WHISPER_BIN = VENDOR / "whisper-cli"
WHISPER_MODEL = VENDOR / "ggml-tiny.en.bin"


class STTError(RuntimeError):
    """whisper.cpp failed."""


def transcribe(wav_path: str) -> str:
    """Return the transcript of a 16 kHz mono 16-bit WAV. Empty string if nothing recognized."""
    proc = subprocess.run(
        [str(WHISPER_BIN), "-m", str(WHISPER_MODEL), "-f", str(wav_path), "-nt", "-np"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise STTError(proc.stderr.strip() or "whisper failed")
    return proc.stdout.strip()
