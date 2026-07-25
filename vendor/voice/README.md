# vendor/voice — bundled STT/TTS binaries + models

The `/api/voice` endpoint shells out to two native binaries. Place these files
here (they are gitignored — large, platform-specific; ship them with the Vercel
deployment, built for the Vercel Linux runtime):

| File | What | Source |
|------|------|--------|
| `whisper-cli` | whisper.cpp CLI binary (Linux) | build from github.com/ggerganov/whisper.cpp |
| `ggml-tiny.en.bin` | whisper `tiny.en` model (~75 MB) | whisper.cpp `models/download-ggml-model.sh tiny.en` |
| `piper` | piper TTS binary (Linux) | github.com/rhasspy/piper releases |
| `en_GB-alan-medium.onnx` (+ `.onnx.json`) | piper `medium` British male voice, ~60 MB — the J.A.R.V.I.S.-style voice | `rhasspy/piper-voices` on huggingface, `en/en_GB/alan/medium/` |

Total stays well under Vercel's function size limit (see Spec B §3). Paths are
referenced by `core/stt.py` and `core/tts.py`; if you change filenames, update
those module constants.

## Wake word ("Hey F.R.I.D.A.Y.")

Wake-word assets live in `static/vendor/` instead — they are small enough to commit
and the browser must fetch them:

| File | What |
|------|------|
| `static/vendor/wakeword/hey_friday.onnx` | custom openWakeWord model for "hey friday" |
| `static/vendor/wakeword/melspectrogram.onnx`, `embedding_model.onnx` | openWakeWord's shared feature extractors (`dscripka/openWakeWord` v0.5.1) |
| `static/vendor/ort/` | onnxruntime-web 1.20.1, wasm backend, single-threaded |

Two consumers, same models: `static/js/wakeword.js` (ear button in the F.R.I.D.A.Y.
panel) and `scripts/wakeword.py` (headless listener, POSTs to `/api/voice`).
