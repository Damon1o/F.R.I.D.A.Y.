# F.R.I.D.A.Y. — Feature Implementation Plan (Specs D–U)

**Date:** 2026-07-24
Specs live in `docs/superpowers/specs/2026-07-24-*.md`. Build in tranches; each
tranche ships tested + committed before the next. TDD, ponytail, existing patterns
(`core.db`, agent `TOOLS`/`dispatch`, `settings` KV, real-Postgres tests).

## Tranche ordering (by cost + dependency)

**Tranche 1 — standalone agent tools (no new infra, no new external keys).**
- **G Weather** — `pages/friday/weather.py` (Open-Meteo, keyless) + `get_weather` tool.
- **I Notes** — `notes` table + `pages/notes/` model/routes + `remember`/`recall`/
  `list_notes`/`delete_note` tools.
- **K NL quick-add** — `POST /api/quickadd` wrapping existing `run_text`.
- **O Music now-playing** — expose existing `SpotifyProvider.get_now_playing` as a
  `get_now_playing` tool (rest of O — queue/volume/playlist — later, needs new
  provider methods).

**Tranche 2 — notification stack.** E (web push) → F (reminders/timers/cron) →
J (daily briefing, needs G). Needs `pywebpush`, VAPID env, Vercel cron.

**Tranche 3 — data-model features.** L (recurring events, `dateutil`), R (todo
tags), Q (unified search, needs I), S (undo).

**Tranche 4 — external/sensitive integrations.** H (web search, needs key),
M (email/Gmail OAuth, sensitive), N (smart-home/Home Assistant), O remainder.

**Tranche 5 — voice/device + hardening.** P (voice context), U (button-to-talk),
T (API auth hardening — gates everything; can pull earlier if deploying publicly),
D (on-device UI, firmware).

## Per-tranche gate
`pytest` green + committed on the feature branch before moving on. Security-flagged
specs (M, T, F cron) get their auth tests written first.
