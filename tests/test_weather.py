"""Spec G weather tool: Open-Meteo parse, default vs explicit location. requests always faked."""
import pages.friday.weather as weather
from pages.friday.tools import dispatch


class FakeResp:
    def __init__(self, ok=True, data=None):
        self.ok = ok
        self._data = data or {}

    def json(self):
        return self._data


FORECAST = {
    "current": {"temperature_2m": 21.0, "weather_code": 3, "wind_speed_10m": 12.0},
    "daily": {"time": ["2026-07-24", "2026-07-25"], "weather_code": [3, 61],
              "temperature_2m_max": [24.0, 22.0], "temperature_2m_min": [15.0, 14.0]},
}


def test_get_weather_explicit_location_geocodes_and_parses(ctx, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResp(True, {"results": [{"latitude": 51.5, "longitude": -0.1, "name": "London"}]})
        return FakeResp(True, FORECAST)
    monkeypatch.setattr(weather.requests, "get", fake_get)

    r = weather.get_weather("London")
    assert r["location"] == "London"
    assert r["current"] == {"temp": 21.0, "conditions": "overcast", "wind": 12.0}
    assert r["forecast"][1]["conditions"] == "light rain"
    assert r["forecast"][0]["hi"] == 24.0


def test_get_weather_unknown_location_errors(ctx, monkeypatch):
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResp(True, {"results": []}))
    assert "error" in weather.get_weather("Nowheresville")


def test_get_weather_no_location_no_home_setting_errors(ctx, monkeypatch):
    # No home_lat/home_lon in settings -> graceful error, no HTTP call.
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResp(False))
    assert "error" in weather.get_weather()


def test_get_weather_uses_home_setting(ctx, monkeypatch):
    from core.db import execute
    for k, v in (("home_lat", "40.7"), ("home_lon", "-74.0"), ("home_name", "NYC")):
        execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (k, v))
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResp(True, FORECAST))
    r = weather.get_weather()
    assert r["location"] == "NYC"


def test_get_weather_service_down_errors(ctx, monkeypatch):
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResp(False))
    from core.db import execute
    for k, v in (("home_lat", "1"), ("home_lon", "2")):
        execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (k, v))
    assert weather.get_weather() == {"error": "weather service unavailable"}


def test_dispatch_get_weather(ctx, monkeypatch):
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResp(True, FORECAST))
    from core.db import execute
    for k, v in (("home_lat", "1"), ("home_lon", "2")):
        execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (k, v))
    assert dispatch("get_weather", {})["current"]["conditions"] == "overcast"
