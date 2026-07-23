# F.R.I.D.A.Y. — ESP32 Voice Client Design (Spec C)

**Date:** 2026-07-23
**Status:** Approved (design). **Implementation gated** on Espressif delivering
the custom `hey friday` WakeNet model.
**Depends on:** Spec A (app on Vercel), Spec B (`POST /api/voice`)
**Related:** Spec D (on-device calendar/todo UI) — separate, future.

## 1. Context

The Waveshare ESP32-S3 7-inch board is F.R.I.D.A.Y.'s voice front end. It listens
for the on-device wake-word `hey friday`, records the command, POSTs it to the
Spec B endpoint, and plays the spoken reply. This spec is the **firmware** for
that loop.

**Implementation is blocked** on one external dependency: ESP-SR WakeNet custom
keywords are provisioned by Espressif (paid, external lead time), so the
`hey friday` model file does not exist yet. Everything else — capture, VAD,
network, playback, display, config — is fully specified here and can be built
the moment the model lands; the model is a drop-in file behind an unchanged
WakeNet API.

The full native calendar/todo UI on the board is **out of scope** (Spec D). Spec
C's display is limited to voice status + transcript/reply text.

## 2. Goals / Non-goals

**Goals**
- Hands-free loop: `hey friday` → record → POST → play reply → idle.
- On-device wake-word (WakeNet) and end-of-speech (VadNet), no cloud round-trip
  to start/stop recording.
- Talk to Spec B over HTTPS with the shared bearer token.
- Minimal LVGL display: four voice states + transcript/reply text.
- All secrets/config out of source (NVS / `sdkconfig`), not hardcoded.

**Non-goals**
- Native calendar/todo UI (Spec D).
- Any STT/TTS/agent logic on-device — all server-side (Spec B).
- OTA updates, multi-board, provisioning UI.
- Barge-in / duplex audio. One utterance, one reply.

## 3. Hardware

- **Board:** Waveshare ESP32-S3 7-inch (ESP32-S3, PSRAM, 7" display).
- **Mic:** onboard I2S microphone → 16 kHz mono 16-bit PCM.
- **Speaker:** onboard I2S speaker/amp for reply playback.
- **Display:** 7" panel driven via LVGL (board BSP).
- **Framework:** ESP-IDF + ESP-SR component (WakeNet + VadNet).

Exact pin/BSP details come from Waveshare's board support package and are pinned
in the plan, not guessed here.

## 4. Firmware loop (state machine)

```
BOOT -> WIFI_CONNECT -> IDLE
IDLE:       WakeNet running on mic stream; on "hey friday" -> LISTENING
LISTENING:  record mic to buffer; VadNet monitors; ~1s silence (or 10s cap) -> THINKING
THINKING:   build WAV; HTTPS POST /api/voice; await response -> SPEAKING
SPEAKING:   play reply WAV over I2S -> IDLE
ERROR:      wifi/POST/parse failure -> show error, backoff, -> IDLE
```

- **16 kHz mono 16-bit** throughout — WakeNet/VadNet input rate and Spec B's
  expected rate. No resampling anywhere.
- Recording capped at ~10s to bound memory (PSRAM buffer) and request size
  (under Spec B's ~2MB cap).

## 5. Networking

- HTTPS POST to `<SERVER_URL>/api/voice` via `esp_http_client` + mbedTLS.
- Headers: `Authorization: Bearer <VOICE_TOKEN>`,
  `Content-Type: multipart/form-data` with one `audio` WAV part.
- TLS: ESP-IDF certificate bundle (Vercel's cert chain), so no pinned cert to
  rotate.
- **Response parsing:** `multipart/mixed` — read the `audio/wav` part into a
  buffer for playback; optionally read the JSON part (`transcript`, `reply`,
  `actions`) for the display. A minimal boundary-split is enough; no full MIME
  library.
- **Failure handling:** wifi disconnect and POST/parse errors → `ERROR` state,
  exponential backoff on reconnect, on-screen message, return to `IDLE`. Never
  wedge; always recover to listening.

## 6. Display (LVGL)

Single screen, driven by the state machine:

| State | Shown |
|-------|-------|
| IDLE | "Say 'hey friday'" / idle indicator |
| LISTENING | listening indicator (mic active) |
| THINKING | working indicator (request in flight) |
| SPEAKING | speaking indicator + reply text |
| ERROR | error message + auto-retry note |

When the JSON sidecar is present, show `transcript` (what it heard) and `reply`
(what it said). Design language mirrors the app where practical (monochrome; no
emoji — icons only), but this is a native LVGL screen, not the web UI.

## 7. Configuration

No secrets in source. Provisioned via NVS (preferred) or `sdkconfig`:

- `WIFI_SSID`, `WIFI_PASSWORD`
- `SERVER_URL` (Vercel deployment base URL)
- `VOICE_TOKEN` (matches Spec B's `VOICE_TOKEN` env var)

Wake-word model: `hey_friday` WakeNet model flashed into its partition; selected
via ESP-SR config. Until Espressif delivers it, a **stock** WakeNet keyword can
stand in behind the same API to exercise the full loop (development only —
called out in the plan, not the shipped config).

## 8. Project layout

```
firmware/
  CMakeLists.txt
  sdkconfig.defaults      # ESP-SR, PSRAM, partition, TLS bundle
  partitions.csv          # app + wake-word model partition
  main/
    CMakeLists.txt
    main.c                # app_main: init, state machine driver
    wake.c/.h             # WakeNet + VadNet: detect + end-of-speech
    audio.c/.h            # I2S capture + playback
    net.c/.h              # HTTPS POST + multipart response parse
    ui.c/.h               # LVGL status screen
    config.c/.h           # NVS/sdkconfig accessors
```

Each unit single-purpose and independently reasoned; `main.c` only wires the
state machine to these modules.

## 9. Testing

Firmware testing is hardware-in-the-loop, not CI:

- **On-device manual:** each state transition; wake trigger; VAD cutoff timing;
  a real command round-trips and plays a reply; error/backoff recovery.
- **Host-testable units where cheap:** the multipart-response parser and the WAV
  header builder are pure functions — unit-test on host with sample buffers.
- No attempt to run WakeNet/VadNet or I2S off-device.

## 10. Risks

- **Wake-word availability** — the gating dependency (Espressif lead time). Loop
  is buildable/testable now with a stock keyword; swap is a file + config change.
- **Board BSP specifics** (I2S pins, display driver) — resolved from Waveshare's
  BSP in the plan.
- **TLS on-device** memory/handshake cost — mitigated by cert bundle and a
  single short-lived request per utterance.
- **VAD tuning** — silence threshold/timeout may need field tuning; parameters
  kept configurable.

## 11. Out of scope (future specs)

- **Spec D:** full native on-device calendar/todo UI reading `/api/*`.
- OTA firmware updates; multi-board provisioning.

## 12. Phase 3 spec set

| Spec | Subsystem | Status |
|------|-----------|--------|
| A | Cloud migration (Vercel + Postgres) | Approved, implement first |
| B | Voice API (`/api/voice`) | Approved, depends on A |
| C | ESP32 voice client (this doc) | Approved, impl gated on wake-word |
| D | On-device calendar/todo UI | Future, not yet specced |
