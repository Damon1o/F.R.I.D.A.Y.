"""Text-to-speech via a bundled piper binary. No Python bindings (stdlib subprocess)."""
import subprocess
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "voice"


def _bin(name: str) -> Path:
    """Windows dev builds are `<name>.exe`; the Vercel Linux build has no suffix."""
    exe = VENDOR / f"{name}.exe"
    return exe if exe.exists() else VENDOR / name


PIPER_BIN = _bin("piper")
PIPER_VOICE = VENDOR / "en_GB-alan-medium.onnx"
# A reply is a few sentences; anything past this is a wedged binary holding a request thread.
TIMEOUT = 60


class TTSError(RuntimeError):
    """piper failed."""


def available() -> bool:
    """False when the gitignored binary/voice are not in vendor/voice (see its README)."""
    return PIPER_BIN.exists() and PIPER_VOICE.exists()


def synth(text: str, out_path: str) -> str:
    """Synthesize `text` to a WAV at out_path (16 kHz mono). Returns out_path."""
    try:
        proc = subprocess.run(
            [str(PIPER_BIN), "-m", str(PIPER_VOICE), "-f", str(out_path)],
            input=text, capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise TTSError("piper timed out")
    if proc.returncode != 0:
        raise TTSError(proc.stderr.strip() or "piper failed")
    return out_path
