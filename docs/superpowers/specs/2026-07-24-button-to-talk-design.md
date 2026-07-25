# F.R.I.D.A.Y. — Button-to-Talk Fallback Design (Spec U)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec B (`/api/voice`), Spec C (ESP32 firmware).

## 1. Context

Spec C's hands-free loop is **blocked** on Espressif delivering the custom
`hey friday` WakeNet model (external lead time). That blocks all on-device voice
testing. This spec adds a **push-to-talk button** path that needs no wake-word,
so the full record → POST → play loop is exercisable **now**, and remains a
permanent fallback if wake-word ever misfires.

Small, unblocks Spec C, and touches only the IDLE→LISTENING trigger.

## 2. Goals / Non-goals

**Goals**
- A physical button (board GPIO / touch region) triggers `IDLE → LISTENING`,
  bypassing WakeNet.
- Everything downstream (VAD cutoff, POST, playback) is Spec C's existing path,
  unchanged.
- Also expose a "talk" button in the **web UI** (browser mic → `/api/voice`) so
  voice is testable with zero hardware.

**Non-goals**
- Replacing wake-word (this is a fallback/dev path; `hey friday` remains the
  primary trigger once available).
- New audio/network/parse code — reuse Spec C modules.

## 3. Design

**Firmware (Spec C):**
- `IDLE` also watches a button GPIO (or LVGL touch button); press → `LISTENING`.
  Same VAD-driven stop and 10s cap. WakeNet path untouched; both triggers coexist.
- Config flag `PTT_ENABLED` (default on until wake-word ships).

**Web UI:**
- A "hold to talk" button records mic audio (MediaRecorder → WAV/PCM), POSTs to
  `/api/voice` with the bearer token, plays the returned reply WAV.
- Lets voice be end-to-end tested from a laptop, decoupling Spec B validation from
  ESP32 hardware entirely.

## 4. Testing

- **Web:** manual — hold, speak, receive + hear reply; asserts Spec B round-trip
  independent of the board.
- **Firmware:** on-device manual — button press enters LISTENING and completes a
  round-trip with a stock/no wake-word model.
- Reuses Spec B's server-side `/api/voice` unit tests (unchanged).

## 5. Risks

- **Mic access in browser** requires HTTPS + user gesture (both satisfied).
- **Audio format** — browser MediaRecorder output must match Spec B's expected
  WAV (16 kHz mono 16-bit); resample/encode client-side or accept and convert
  server-side — decide in plan.
- **Debounce** the physical button to avoid double-triggers.
