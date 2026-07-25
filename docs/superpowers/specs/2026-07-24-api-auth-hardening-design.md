# F.R.I.D.A.Y. — API Auth Hardening Design (Spec T)

**Date:** 2026-07-24
**Status:** Draft (design). **Security.**
**Depends on:** Spec A. **Unblocks:** Spec D open-Q1 (board API access).

## 1. Context

The app is single-user but the `/api/*` routes (events, todos, music, settings,
friday) are effectively open — anyone who reaches the deployment URL can read and
mutate data. Spec B added a `VOICE_TOKEN` bearer on `/api/voice`; Spec D needs the
board to read the data API. This spec puts a consistent auth gate on the whole
API surface and adds basic rate limiting.

## 2. Goals / Non-goals

**Goals**
- A single auth layer protecting `/api/*` (and pages, as appropriate): the user's
  browser session, plus a bearer token for device/cron callers (board, Spec F cron).
- Fail-closed: unauthenticated `/api/*` → 401.
- Light rate limiting on unauthenticated/auth-attempt paths.
- Consolidate the existing `VOICE_TOKEN`/`CRON_SECRET` bearer checks into one
  helper.

**Non-goals**
- Multi-user accounts/roles (still single user).
- OAuth login UI overhaul — a single app password/passphrase login is enough.
- WAF/DDoS (Vercel platform concern; BotID optional later).

## 3. Design

- **Session auth for the human:** a minimal login (one `APP_PASSWORD` env,
  server-set signed session cookie) gating pages + `/api/*`. Flask `before_request`
  on the API blueprints rejects unauthenticated with 401.
- **Bearer auth for devices/cron:** `Authorization: Bearer <token>` accepted where
  a device needs access — the board's read/PATCH (Spec D), voice (`VOICE_TOKEN`),
  cron (`CRON_SECRET`). One `require_auth()` helper checks session **or** an allowed
  bearer, per-route configurable which bearers are valid.
- **Rate limit:** a simple in-Postgres or in-memory counter on login + bearer
  failures (bounded attempts/min) → 429. Keep minimal; single user.
- **Spec D:** resolves open-Q1 — the board sends its bearer to the (now gated)
  read routes, or to the `/api/board` aggregate, both behind `require_auth`.

## 4. Security requirements

- All tokens/passwords from env, never source; fail-closed on missing config
  (empty `APP_PASSWORD` must not mean "open").
- Constant-time token comparison (`hmac.compare_digest`).
- HTTPS only (Vercel default); `Secure`+`HttpOnly`+`SameSite` on the session cookie.
- Bearer tokens scoped: the board token grants only the board's routes, not full
  API mutation, where practical.

## 5. Testing

- Unit: unauthenticated `/api/*` → 401; valid session → 200; valid bearer → 200;
  wrong bearer → 401.
- Unit: `compare_digest` used (no early-return on length); empty env → fail-closed.
- Unit: rate limiter returns 429 after N failures.

## 6. Risks

- **Lockout** — a forgotten `APP_PASSWORD` locks the single user out; recovery is
  re-setting the env var (documented).
- **Breaking existing clients** — the web UI must log in; the board/cron must send
  bearers. Roll out with all callers updated together.
