# F.R.I.D.A.Y. — Voice Notes Design (Spec V)

**Date:** 2026-08-01
**Status:** Ready to implement. **Small — most of this already works.**
**Depends on:** Spec A (tool loop), voice pipeline (`pages/voice/routes.py`,
`static/js/voice-web.js`), notes/todos tools.
**Estimate:** ~45 minutes.

## 1. Context — what already exists

Before writing code, the honest state of the repo:

- `static/js/voice-web.js` already transcribes speech (Web Speech API, falling
  back to `/api/voice/stt` → whisper.cpp) and calls `submitTranscript()`.
- `submitTranscript()` already feeds the agent loop.
- The agent already has `create_todo`, `create_event`, and `remember` (notes).

So **"say 'add milk to my list' and get a todo" already works today.** No spec
needed for that path. This spec covers only the one thing that does not:
**raw dictation** — capturing a long spoken thought verbatim, without the model
reinterpreting, truncating, or turning it into a task.

## 2. Goals / Non-goals

**Goals**
- A dictation mode where the transcript is stored verbatim as a note.
- Reachable by voice ("take a note", "dictate"), and confirmed back so the user
  knows it landed.

**Non-goals**
- A new recorder, a new STT path, a new page, a notes UI. All exist.
- Audio file retention. Text only; the WAV is already discarded post-transcribe.
- Speaker diarisation, punctuation restoration, multi-minute recordings.

## 3. Design

The laziest thing that works is **one tool plus one prompt line** — no client
changes at all, because the transcript already reaches the agent.

**Tool** (`pages/friday/tools.py`) — thin wrapper on the existing note model:

```python
_fn("take_note", "Store the user's words verbatim as a note. Use when they say "
    "'take a note', 'dictate', or 'remember this exactly'. Do not summarise, "
    "rephrase, shorten, or turn it into a todo — store the text as spoken.", {
        "text": {"type": "string", "description": "The user's words, unedited."},
    }, ["text"]),
```

```python
if name == "take_note":
    return notes.create_note(args["text"])
```

`take_note` is deliberately a second name for `notes.create_note`, alongside the
existing `remember`. `remember` is for facts the assistant should recall later
("I'm allergic to shellfish"); `take_note` is for verbatim capture. Same
storage, different instruction to the model — that difference is the whole
feature, and it costs three lines.

**System prompt** (`pages/friday/agent.py`), one line:

> When the user asks you to take a note or dictate, call `take_note` with their
> exact words. Preserve their wording — do not summarise or tidy it.

**Confirmation:** the agent's normal reply is the confirmation ("Noted."), and
TTS already speaks it. Nothing extra.

## 4. Known ceiling

Web Speech API stops on a pause (roughly 5–10 seconds of silence), so a long
dictation can end early. Not solved here — mark it in code:

```python
# ponytail: dictation ends at the browser's speech-pause cutoff. If long-form
# capture matters, switch dictation to the MediaRecorder + /api/voice/stt path,
# which records until the user stops it.
```

Upgrade path is written down; build it when a real dictation gets truncated.

## 5. Testing

Add to `tests/test_friday.py`:

1. `dispatch("take_note", {"text": "..."})` persists the text unchanged
   (byte-identical, including punctuation and casing).
2. Missing `text` returns `{"error": "missing argument 'text'"}` via the
   existing `KeyError` handler — no raise.

Existing voice tests cover the transcription path; do not duplicate them.

## 6. Skipped deliberately

A dedicated dictation UI, a `/voice-notes` page, audio storage, a distinct
`voice_notes` table. Notes already have storage, search, and a page — reusing
them is the entire point.
