# F.R.I.D.A.Y. — Daily Briefing Design (Spec J)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A, Spec G (weather).
**Related:** Spec E (push the briefing), Spec B (voice-read the briefing), Spec D
(board can show it).

## 1. Context

The Iron-Man "good morning" moment: one assembled summary of the day — today's
agenda, top open todos, and current weather — surfaced on the dashboard, pushable
each morning, and readable aloud by voice. Pure composition over existing data;
no new data model.

## 2. Goals / Non-goals

**Goals**
- `briefing.build()` → a structured summary `{date, greeting, events, todos, weather}`.
- Dashboard card renders it on load.
- `GET /api/briefing` (JSON) and a text form for voice/push.
- Optional morning push at a user-set time (via Spec E + Spec F cron scan).

**Non-goals**
- News/email/traffic in the briefing (weather + agenda + todos only; email is a
  separate tool, Spec M).
- Configurable briefing sections/ordering UI. Fixed layout for now.
- Generating the greeting via the LLM (a cheap templated greeting is enough;
  don't spend a model call on "Good morning").

## 3. Design

**Module** `pages/dashboard/briefing.py`:
- `build()` gathers: `events.list_events(today, tomorrow)`,
  `todos.list_todos(done=False)` (top few by due), `weather.get_weather()`
  (Spec G; skipped gracefully if unavailable), a templated time-of-day greeting.
- `to_text()` → a short paragraph for TTS/push.

**Routes:** `GET /api/briefing` returns `build()`. Dashboard template fetches it.

**Morning push (optional):** a `briefing_push_time` setting; the Spec F cron scan
checks it once/day and calls `notify.push("Good morning", briefing.to_text())`.

**Voice:** the agent gains no new tool necessarily — but adding a `get_briefing`
tool lets "give me my briefing" work by voice; it returns `to_text()`.

## 4. Testing

- Unit: `build()` with faked models/weather assembles all sections; weather-down
  path omits weather without error.
- Unit: `to_text()` renders a sane sentence; greeting varies by hour (inject clock).
- Unit: `/api/briefing` returns the structure.

## 5. Risks

- **Weather coupling** — briefing must not fail if Spec G errors; treat weather as
  optional.
- **Timezone for "today"** — use the user's tz from settings when bounding the day.
