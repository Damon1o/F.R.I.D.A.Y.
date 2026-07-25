# F.R.I.D.A.Y. — Voice Conversation Context Design (Spec P)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A, Spec B (`/api/voice`, `run_text`).

## 1. Context

The web chat persists turns in the `messages` table, so it's multi-turn. The voice
endpoint (`run_text`) currently runs each utterance fresh — "move it to 3pm" has no
"it". This spec gives voice the same short conversational memory so follow-ups
resolve against recent turns.

## 2. Goals / Non-goals

**Goals**
- Voice turns share the same `messages` history the chat uses, so references
  ("it", "that one", "the second") resolve.
- A bounded context window (last N turns / token budget) so the prompt stays small.
- Idle timeout: after inactivity, voice starts a fresh context (a new "session").

**Non-goals**
- Separate per-channel histories. One assistant, one conversation (voice + web
  share it) — simplest and matches the single-user model.
- Long-term semantic memory (that's Spec I notes/`recall`).
- Speaker diarization / multi-user.

## 3. Design

- `run_text` gains an optional history load: prepend the last N `messages` (same
  `to_api()` used by chat) before the user's utterance, and persist the voice
  user/assistant turns back to `messages` (so web and voice interleave).
- **Window bound:** cap at last N turns (default ~10) or a token budget; older
  turns dropped from the prompt (still in DB).
- **Session boundary:** a `last_voice_at` marker; if the gap exceeds a timeout
  (default ~5 min), don't load prior turns (fresh start) to avoid stale "it".
- No schema change — reuses `messages`.

## 4. Testing

- Unit: two sequential `run_text` calls — the second resolves a pronoun using the
  first's created entity (faked LLM asserted to receive prior turns in the prompt).
- Unit: window cap trims to N turns.
- Unit: after simulated idle-timeout, prior turns are NOT included.

## 5. Risks

- **Context bleed** — a stale reference across a long gap; mitigated by the idle
  timeout.
- **Prompt growth/cost** — bounded window keeps token cost flat.
- **Interleaving order** — voice and web writes to `messages` must stay
  chronologically correct (single user, low concurrency — fine).
