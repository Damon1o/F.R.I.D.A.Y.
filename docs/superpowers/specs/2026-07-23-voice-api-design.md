# F.R.I.D.A.Y. — Voice API Design (Spec B)

**Date:** 2026-07-23
**Status:** Approved (design), pending implementation plan
**Depends on:** Spec A (Cloud migration — app on Vercel + Postgres)
**Blocks:** Spec C (ESP32 firmware)

## 1. Context

With the app on Vercel (Spec A), the voice subsystem adds one endpoint,
`POST /api/voice`, that turns a spoken clip into a spoken reply while driving the
existing F.R.I.D.A.Y. agent. The Waveshare ESP32-S3 board (Spec C) records after
its on-device `hey friday` wake-word, POSTs the audio here, and plays the reply.

This spec covers the **server endpoint only**. On-device wake-word, recording,
and playback are Spec C. Cloud runtime and the database are Spec A.

## 2. Goals / Non-goals

**Goals**
- One endpoint: WAV in, spoken reply out, agent acts on todos/events in between.
- Speech-to-text and text-to-speech run **in the Vercel function** (bundled
  binaries + models), no third-party STT/TTS service.
- Reuse the existing agent tool-loop and shared conversation history unchanged.
- Fit inside Vercel's 250MB function limit.
- Guard the now-public endpoint with a shared token.

**Non-goals**
- Wake-word, VAD, recording, playback (Spec C, on-device).
- Streaming audio / real-time duplex. One request, one reply.
- Multi-user, per-request voices, or voice selection.
- Changing web chat, agent tools, templates, or the DB schema.

## 3. Size budget (the hard constraint)

Vercel caps an unzipped function at **250MB**. Chosen models keep the whole
function well under that:

| Asset | Size |
|-------|------|
| `whisper-cli` binary (Linux glibc, static-ish) | ~5MB |
| `tiny.en` ggml model | ~75MB |
| `piper` binary | ~5MB |
| piper `low` voice (`.onnx` + `.json`) | ~20MB |
| psycopg + flask + app | ~40–60MB |
| **Total** | **~145–165MB (fits)** |

Trade-off accepted: `tiny.en` is less accurate than `base.en`, and the `low`
voice is thinner. Acceptable for short wake-word-gated commands. Revisit only if
recognition proves poor in practice — options then are `base.en` fetched to
`/tmp` on cold start, or moving voice compute off serverless (both rejected now
as heavier).

## 4. Endpoint contract (the B↔C interface)

```
POST /api/voice
Authorization: Bearer <VOICE_TOKEN>
Content-Type: multipart/form-data
  part "audio": WAV, PCM 16 kHz mono 16-bit
```

Response on success (`200`):

```
Content-Type: multipart/mixed; boundary=...
  part 1  application/json  {"transcript": "...", "reply": "...", "actions": [...]}
  part 2  audio/wav         reply.wav  (piper low, 16 kHz mono)
```

- **16 kHz mono 16-bit** is whisper's native input rate — no server-side
  resample, and it is what the board records.
- `actions` is the list of tool names the agent invoked this turn (e.g.
  `["create_todo"]`), for on-device logging/UI. Optional for the board to read.
- The board may ignore the JSON part and just play part 2.

Errors:

| Case | Status | Body |
|------|--------|------|
| Missing/bad token | 401 | JSON `{"error": "unauthorized"}` |
| No audio part / empty | 400 | JSON `{"error": "no audio"}` |
| Audio over size cap | 413 | JSON `{"error": "audio too large"}` |
| STT produced empty text | 200 | normal multipart; reply = a spoken "I didn't catch that." |
| LLM/agent error | 200 | normal multipart; reply = the agent's error sentence, spoken |

Returning a **spoken** reply for empty-STT and agent errors keeps the board's
job trivial: any `200` means "play the audio". Only auth/size/malformed-request
failures are non-`200`.

Size cap: reject bodies over a small limit (e.g. 2MB — ~60s of 16 kHz mono
16-bit is ~1.9MB) to bound `/tmp` use and transcription time.

## 5. Components

New, small, single-purpose:

```
pages/voice/__init__.py
pages/voice/routes.py     # voice_bp: POST /api/voice — auth, parse, orchestrate, respond
core/stt.py               # transcribe(wav_path) -> str   (whisper-cli subprocess)
core/tts.py               # synth(text) -> wav_path        (piper subprocess)
vendor/voice/             # whisper-cli, piper binaries + tiny.en + low voice
```

Reused unchanged:

- `pages/friday/agent.py` — new `run_text(user_text, client=None) -> dict`
  helper beside `run_turn`. Runs the **same** tool loop; instead of yielding SSE
  frames it returns `{"reply": str, "actions": [tool_name, ...]}`. Both share
  `_system()`, `_args`, `dispatch`, and `messages`. No behavioral change to the
  streaming web path.
- `pages/friday/messages.py` — voice turns persist here, so voice and web chat
  share one history (single user, one assistant).

### 4-step orchestration in `routes.py`

1. Auth: const-time compare `Authorization` bearer vs `VOICE_TOKEN`; else 401.
2. Parse: read `audio` part → `/tmp/in.wav`; guard empty/oversize.
3. `transcript = stt.transcribe("/tmp/in.wav")`; if blank → reply text =
   "I didn't catch that." (skip agent).
4. else `result = agent.run_text(transcript)`; `wav = tts.synth(result["reply"])`;
   build multipart(JSON, wav bytes); delete `/tmp` files.

### `core/stt.py` / `core/tts.py`

Thin `subprocess.run` wrappers around the bundled binaries, reading/writing
`/tmp`. No Python bindings (avoids a compiled dependency; ponytail). Binary and
model paths from module constants pointing at `vendor/voice/`. Each raises a
small typed error on non-zero exit, mapped to a spoken fallback in step 3/4.

## 6. Config

`config.py`: add `VOICE_TOKEN = os.environ.get("VOICE_TOKEN", "")`. Empty token
in a deployed env means the endpoint refuses every request (fail closed).

Vercel env vars (added to Spec A's set): `VOICE_TOKEN`.

`vercel.json`: `/api/voice` covered by the existing catch-all route to the Flask
handler; `maxDuration` already set for Pro in Spec A.

## 7. Security

- Endpoint is public (Vercel). Shared **bearer token**, compared in constant
  time, is the single guard — single-user-appropriate (ponytail; HMAC rejected
  as overkill). Token stored in Vercel env server-side and in board flash
  (Spec C), only ever sent over HTTPS.
- Fail closed: no/empty `VOICE_TOKEN` env ⇒ all requests 401.
- Size cap bounds `/tmp` and CPU. `/tmp` files deleted after each request
  (also wiped on function recycle).
- No new attack surface on web routes; auth applies to `/api/voice` only.

## 8. Testing

- `core/stt.py` / `core/tts.py`: tests monkeypatch `subprocess.run` — assert the
  binary/model/paths in the argv and the parsing of output; do **not** invoke
  real binaries in CI (models not in the test image).
- `pages/voice/routes.py`: Flask test client with STT/TTS and `run_text`
  monkeypatched (LLM already faked per Spec A conftest). Assert 401 on bad token,
  400 on missing audio, 413 on oversize, and a well-formed multipart on success.
- `agent.run_text`: reuse the existing `FakeClient` to assert it runs the tool
  loop and returns `{"reply", "actions"}` with history persisted — mirrors the
  existing `run_turn` tests.
- Latency is not asserted in CI (no real models).

## 9. Risks

- **tiny.en accuracy** on short commands — the main quality risk; mitigation
  path documented in §3.
- **Binary compatibility** with Vercel's Linux runtime — binaries must be built
  for that glibc/arch; verified in the plan, not assumed.
- **Cold-start CPU** for transcription on a fresh function — tiny.en on a few
  seconds of audio is ~1–2s; comfortably inside 60s.
- **`/tmp` space** — bounded by the size cap and per-request cleanup.

## 10. What stays exactly the same

Web chat SSE path (`run_turn`), agent tools, DB schema, templates, static
assets, and every existing route. Voice is additive: one blueprint, two
subprocess wrappers, one non-streaming agent helper.

## 11. Open items folded into the plan

- Exact bundled binary builds/versions and where they're vendored from.
- Multipart response assembly (hand-built vs a tiny helper).
- Whether `run_text` and `run_turn` share a common private core to avoid drift.
