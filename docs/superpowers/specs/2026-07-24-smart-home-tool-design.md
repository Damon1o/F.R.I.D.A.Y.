# F.R.I.D.A.Y. — Smart-Home Tool Design (Spec N)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A.

## 1. Context

The Iron-Man beat: "FRIDAY, turn off the lights." Add a smart-home control tool.
To avoid tying FRIDAY to one vendor's cloud, target **Home Assistant** as the
single integration point — it already abstracts lights/plugs/switches/scenes
across brands behind one REST API and long-lived token.

## 2. Goals / Non-goals

**Goals**
- `list_devices()`, `set_device(name, state)` (on/off/brightness), `run_scene(name)`.
- One backend: Home Assistant REST API + long-lived access token.
- Friendly-name matching so voice/text can say "kitchen lamp".

**Non-goals**
- Direct per-vendor SDKs (Kasa/Hue/etc.) — HA already unifies them; don't
  reimplement device drivers (YAGNI).
- Local network discovery from the Vercel serverless app (it can't reach a LAN);
  requires HA exposed via its own remote URL (Nabu Casa or user's tunnel).
- Camera/media/climate automations beyond on/off/brightness/scene in v1.

## 3. Design

**Tools** (add to `TOOLS` + `dispatch`):
- `list_devices` → HA `/api/states` filtered to `light.`/`switch.` domains →
  `[{name, state}]`.
- `set_device` {`name`, `state`} → resolve friendly name → entity_id → call
  `/api/services/light|switch/turn_on|off` (brightness in the payload).
- `run_scene` {`name`} → `/api/services/scene/turn_on`.

**Module** `pages/friday/home.py` — `requests` against `HOME_ASSISTANT_URL` with
`Authorization: Bearer <HOME_ASSISTANT_TOKEN>`. Env-configured; missing config →
`{"error": "smart home not configured"}`.

**Name matching:** case-insensitive contains match on friendly_name; ambiguous →
return the candidates so the agent can ask.

## 4. Testing

- Unit: map HA `/api/states` JSON → device list; name→entity resolution incl.
  ambiguous case.
- Unit: `set_device` builds the correct service call/payload (faked HTTP).
- Unit: unconfigured env → graceful error.

## 5. Risks

- **Reachability** — serverless → HA needs a public/remote HA URL; documented as a
  prerequisite. No LAN access from Vercel.
- **Security** — the HA token grants home control; store in env only, never logged.
  Consider a scoped HA user. HTTPS required.
- **Latency/availability** — HA down → graceful error, agent tells the user.
