"""Text-to-speech via a bundled piper binary. No Python bindings (stdlib subprocess)."""
import subprocess
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "voice"
PIPER_BIN = VENDOR / "piper"
PIPER_VOICE = VENDOR / "en_GB-alan-medium.onnx"


class TTSError(RuntimeError):
    """piper failed."""


def synth(text: str, out_path: str) -> str:
    """Synthesize `text` to a WAV at out_path (16 kHz mono). Returns out_path."""
    proc = subprocess.run(
        [str(PIPER_BIN), "-m", str(PIPER_VOICE), "-f", str(out_path)],
        input=text, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise TTSError(proc.stderr.strip() or "piper failed")
    return out_path
