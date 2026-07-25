# F.R.I.D.A.Y. — Reminders & Timers Design (Spec F)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A, Spec E (Web Push delivery).
**Related:** Spec B/voice (tools callable by voice), Spec D (board can show/alert).

## 1. Context

Core assistant primitive that's missing: "remind me to call the dentist at 3pm",
"set a 10-minute timer". Also covers **todo due-date reminders** (fire when a
todo's `due_at` arrives) and is the substrate for **proactive voice** ("event in
10 minutes"). All delivery goes through Spec E's `push()`.

The hard part on Vercel serverless is *firing at a time* — no always-on process.
Solved with **Vercel Cron** hitting a due-scan endpoint every minute.

## 2. Goals / Non-goals

**Goals**
- Agent tools: `set_reminder(when, text)`, `set_timer(duration, label?)`,
  `list_reminders`, `cancel_reminder(id)`.
- A `reminders` table; a cron-driven scanner that fires due rows via `push()`.
- Event "starts soon" and todo "due now" reminders reuse the same scan.

**Non-goals**
- Sub-minute precision (cron granularity is 1 min — fine for human reminders).
- Recurring reminders (fold into Spec L recurrence if wanted later).
- SMS/email delivery (push only; email is Spec M's own tool).

## 3. Design

**Tools** (add to `pages/friday/tools.py` `TOOLS` + `dispatch`):
- `set_reminder` {`fire_at` ISO, `text`} → insert `reminders` row.
- `set_timer` {`seconds`, `label`?} → compute `fire_at = now + seconds`, insert.
- `list_reminders` / `cancel_reminder` {`reminder_id`}.

**Scanner** (`pages/notify/scan.py`, `GET /api/cron/scan`):
1. Select `reminders` where `fired_at IS NULL AND fire_at <= now()`.
2. For each: `notify.push(...)`, set `fired_at = now()`.
3. Also: events starting within a lead window (default 10 min) not yet alerted,
   and open todos whose `due_at <= now()` not yet alerted — same push path,
   dedup via an `alerted_at` marker (events/todos get a nullable `alerted_at`).

Cron endpoint gated by a `CRON_SECRET` bearer (Vercel sends it), fail-closed.

**vercel.json / vercel.ts:** `crons: [{ path: '/api/cron/scan', schedule: '* * * * *' }]`.

## 4. Data

```sql
CREATE TABLE reminders (
  id SERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  fire_at TIMESTAMPTZ NOT NULL,
  fired_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- events, todos gain: alerted_at TIMESTAMPTZ  (nullable)
```

## 5. Testing

- Unit: scanner with frozen `now` + faked `push` — fires only due, unfired rows;
  sets `fired_at`; idempotent on a second run (no double-fire).
- Unit: each tool inserts/cancels correctly; `set_timer` math.
- Unit: event lead-window + todo-due selection with `alerted_at` dedup.

## 6. Risks

- **Cron auth** — endpoint must reject non-cron callers (`CRON_SECRET`), else
  anyone can trigger scans. Fail-closed like Spec B's `VOICE_TOKEN`.
- **Double-fire on overlapping cron runs** — `fired_at`/`alerted_at` guard makes
  the scan idempotent.
- **Missed minute** (cron skip) — next run catches `fire_at <= now()`; late is
  acceptable for human reminders.
