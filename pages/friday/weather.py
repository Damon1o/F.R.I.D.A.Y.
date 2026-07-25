"""Spec G — weather via Open-Meteo (keyless). Pure HTTP + parse; DB only for defaults."""
import requests

from core.db import query

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather-interpretation codes -> short label.
_CODES = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm w/ hail", 99: "thunderstorm w/ heavy hail",
}


def _label(code) -> str:
    return _CODES.get(code, "unknown")


def _setting(key, default=None):
    try:
        row = query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
        return row["value"] if row else default
    except Exception:
        return default


def _geocode(location: str):
    resp = requests.get(GEOCODE_URL, params={"name": location, "count": 1}, timeout=10)
    results = resp.json().get("results") if resp.ok else None
    if not results:
        return None
    r = results[0]
    return r["latitude"], r["longitude"], r.get("name", location)


def get_weather(location: str = None) -> dict:
    """Current conditions + a short daily forecast. Returns {"error": ...} on any failure."""
    if location:
        geo = _geocode(location)
        if not geo:
            return {"error": f"could not find location: {location}"}
        lat, lon, name = geo
    else:
        lat, lon = _setting("home_lat"), _setting("home_lon")
        if not lat or not lon:
            return {"error": "no location given and no home location set"}
        name = _setting("home_name", "home")

    imperial = _setting("units", "metric") == "imperial"
    resp = requests.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
        "timezone": "auto", "forecast_days": 3,
    }, timeout=10)
    if not resp.ok:
        return {"error": "weather service unavailable"}

    d = resp.json()
    cur, daily = d.get("current", {}), d.get("daily", {})
    forecast = [
        {"date": date, "hi": daily["temperature_2m_max"][i],
         "lo": daily["temperature_2m_min"][i], "conditions": _label(daily["weather_code"][i])}
        for i, date in enumerate(daily.get("time", []))
    ]
    return {
        "location": name,
        "current": {"temp": cur.get("temperature_2m"),
                    "conditions": _label(cur.get("weather_code")),
                    "wind": cur.get("wind_speed_10m")},
        "forecast": forecast,
    }
