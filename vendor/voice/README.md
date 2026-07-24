# vendor/voice — bundled STT/TTS binaries + models

The `/api/voice` endpoint shells out to two native binaries. Place these files
here (they are gitignored — large, platform-specific; ship them with the Vercel
deployment, built for the Vercel Linux runtime):

| File | What | Source |
|------|------|--------|
| `whisper-cli` | whisper.cpp CLI binary (Linux) | build from github.com/ggerganov/whisper.cpp |
| `ggml-tiny.en.bin` | whisper `tiny.en` model (~75 MB) | whisper.cpp `models/download-ggml-model.sh tiny.en` |
| `piper` | piper TTS binary (Linux) | github.com/rhasspy/piper releases |
| `en_US-low.onnx` (+ `.json`) | piper `low`-quality US English voice (~20 MB) | piper voices (huggingface rhasspy/piper-voices) |

Total stays well under Vercel's 250 MB function limit (see Spec B §3). Paths are
referenced by `core/stt.py` and `core/tts.py`; if you change filenames, update
those module constants.
