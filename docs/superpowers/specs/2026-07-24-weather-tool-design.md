# F.R.I.D.A.Y. — Weather Tool Design (Spec G)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (agent tool loop).
**Related:** Spec J (daily briefing consumes this).

## 1. Context

"What's the weather" is a baseline assistant answer FRIDAY can't give. Add a
`get_weather` agent tool backed by **Open-Meteo** (no API key, free, permissive).
Small, self-contained, and a dependency of the daily briefing (Spec J).

## 2. Goals / Non-goals

**Goals**
- `get_weather(location?)` tool → current conditions + short daily forecast.
- Default location from `settings` when the user omits one.
- Geocode a named place via Open-Meteo's geocoding endpoint.

**Non-goals**
- Radar, hourly, severe-weather alerts, historical data.
- A paid/keyed provider. Open-Meteo is enough for a personal assistant.
- A weather dashboard widget (Spec J surfaces it; not this spec).

## 3. Design

**Tool** (add to `TOOLS` + `dispatch`):
- `get_weather` {`location`?: string} →
  - resolve lat/lon: if `location` given, hit geocoding API; else read
    `settings['home_lat']`/`['home_lon']` (set on settings page).
  - `GET api.open-meteo.com/v1/forecast?...current=...&daily=...`
  - return `{location, current: {temp, code, wind}, forecast: [{date, hi, lo, code}]}`,
    weather `code` mapped to a short text label.

**Module** `pages/friday/weather.py` — pure HTTP + parse (uses `requests`, already
a dep). No DB except the settings read for default coords.

**Settings:** `home_lat`, `home_lon`, `units` (metric/imperial) on the settings page.

## 4. Testing

- Unit: parse a canned Open-Meteo JSON into the tool's return shape; code→label map.
- Unit: default-location path reads settings; explicit-location path geocodes
  (both with faked `requests`).

## 5. Risks

- **Open-Meteo downtime/schema change** — tool returns `{"error": ...}` so the
  LLM degrades gracefully ("couldn't get weather"), never raises.
- **Units confusion** — pass `temperature_unit`/`wind_speed_unit` from settings.
