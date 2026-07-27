"""Keyless reference lookups: exchange rates (Frankfurter) and public holidays (Nager.Date).

Same shape as weather.py — pure HTTP + parse, {"error": ...} on any failure.
"""
import requests

from core.clock import now, tz

RATES_URL = "https://api.frankfurter.dev/v1/latest"
HOLIDAYS_URL = "https://date.nager.at/api/v3/PublicHolidays"


def get_datetime(timezone: str = None) -> dict:
    """Authoritative current date/time. The LLM must not compute this itself."""
    dt = now()
    if timezone:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            dt = dt.astimezone(ZoneInfo(timezone))
        except (ZoneInfoNotFoundError, ValueError):
            return {"error": f"unknown timezone: {timezone}"}
    hour12 = dt.hour % 12 or 12  # %-I is not portable to Windows, so format by hand
    return {
        "iso": dt.isoformat(timespec="seconds"),
        "spoken": f"{hour12}:{dt:%M %p} on {dt:%A}, {dt:%B} {dt.day}, {dt.year}",
        "date": dt.date().isoformat(),
        "time_24h": dt.strftime("%H:%M"),
        "weekday": dt.strftime("%A"),
        "timezone": timezone or str(tz()),
        "utc_offset": dt.strftime("%z"),
    }


def convert_currency(amount: float, base: str, target: str) -> dict:
    """Convert `amount` from one ISO-4217 currency to another at today's ECB rate."""
    base, target = base.upper(), target.upper()
    try:
        resp = requests.get(
            RATES_URL, params={"base": base, "symbols": target, "amount": amount}, timeout=10
        )
    except requests.RequestException:
        return {"error": "currency service unavailable"}
    if not resp.ok:
        return {"error": f"unknown currency: {base} or {target}"}

    d = resp.json()
    value = d.get("rates", {}).get(target)
    if value is None:
        return {"error": f"no rate for {base} to {target}"}
    return {"amount": amount, "from": base, "to": target, "result": value, "date": d.get("date")}


def list_holidays(country: str = "US", year: int = None) -> list | dict:
    """Public holidays for an ISO-3166 country code, defaulting to the current year."""
    country, year = country.upper(), year or now().year
    try:
        resp = requests.get(f"{HOLIDAYS_URL}/{year}/{country}", timeout=10)
    except requests.RequestException:
        return {"error": "holiday service unavailable"}
    if not resp.ok:
        return {"error": f"no holiday data for {country}"}
    return [{"date": h["date"], "name": h["localName"], "global": h.get("global", True)}
            for h in resp.json()]
