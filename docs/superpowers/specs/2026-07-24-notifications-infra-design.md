# F.R.I.D.A.Y. — Notifications Infrastructure Design (Spec E)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (Flask on Vercel + Postgres).
**Blocks:** Spec F (reminders/timers), Spec J (daily briefing push), proactive
voice.

## 1. Context

FRIDAY can create todos/events but cannot **tell the user anything unprompted**.
Reminders, timers, due-date alerts, and the morning briefing all need one shared
delivery channel. This spec builds that channel once — the **Web Push** primitive
— so later specs (F, J) just enqueue a notification instead of each reinventing
delivery.

Single-user app, so a single push subscription (the user's browser/phone) is
enough. No fan-out, no per-user topics.

## 2. Goals / Non-goals

**Goals**
- A service worker that receives Web Push and shows a notification.
- Store the browser `PushSubscription` server-side (in `settings`).
- A server helper `push(title, body, url=None)` any feature can call.
- VAPID keys via env (no third-party push service).

**Non-goals**
- Native mobile push (APNs/FCM). Web Push covers browser + installed PWA.
- Scheduling logic (Spec F owns *when*; E owns *how*).
- Multi-device fan-out, notification history UI, per-category prefs (YAGNI now).

## 3. Design

**Client** (`static/js/push.js` + `static/sw.js`):
- On the settings page, a "Enable notifications" toggle requests permission,
  subscribes with the VAPID public key, POSTs the subscription JSON.
- `sw.js` handles `push` → `showNotification`; `notificationclick` → focus/open
  the `url`.

**Server** (`pages/notify/`):
- `POST /api/push/subscribe` — store the subscription JSON in `settings`
  (`key='push_subscription'`), same upsert pattern as Spotify tokens.
- `POST /api/push/test` — send a test push (guards the wiring).
- `notify.push(title, body, url=None)` — load subscription, send via `pywebpush`.
  Best-effort: swallow/ log a `410 Gone` and clear the stored subscription
  (subscription expired), never raise into the caller.

**Env:** `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (mailto:).

**Dependency:** `pywebpush` (one lib; do not hand-roll VAPID/JWT/ECDH).

## 4. Data

Reuse `settings` KV — no new table. Keys: `push_subscription` (JSON blob).

## 5. Testing

- Unit: `notify.push` with a faked `pywebpush` — asserts payload shape, and that
  a simulated `410` clears the stored subscription without raising.
- Unit: subscribe endpoint upserts the blob.
- Manual: enable on settings page, receive `/api/push/test` notification.

## 6. Risks

- **Serverless statelessness** — no in-memory subscription; always read from
  `settings`. Fine, one row.
- **VAPID key rotation** invalidates subscriptions — documented in `.env.example`;
  re-subscribe on next settings visit.
- **iOS Web Push** requires the PWA be installed to home screen — note in UI.
