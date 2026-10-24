"""Forecast providers for Harvestly, normalised to one shape and cross-checkable (stdlib only).

Every fetcher returns a list of dicts for the days AFTER today, oldest first:
    {"day": date, "temp_c": float, "rh": float, "rain_mm": float|None, "rain_prob": float|None}
which maps one-to-one onto engine.WeatherDay.

Facts checked live on 13 Oct 2026 for Kitale (1.0157, 35.0062); see docs/WEATHER_PROVIDERS.md:
  open-meteo   7 days (up to 16), no key, free tier NON-COMMERCIAL, CC BY 4.0 credit required
  weatherapi   free plan 3-day forecast, commercial use allowed, link back asked; the key starts on a 14-day Business
               trial (14-day forecast) and drops to Free afterwards, so nothing may rely on more than 3 days
  openweather  free 5-day / 3-hour forecast, key works; One Call 3.0 needs a separate subscription (401)
The engine wants 7 days; days beyond what a provider returns are filled by the engine's own rule (the mean of the forecast).
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

KITALE = (1.0157, 35.0062)
TZ_EAT = timezone(timedelta(hours=3))      # Kitale: Africa/Nairobi, no DST
TIMEOUT = 15


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "harvestly-prototype/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def open_meteo(lat, lon, today, fetch=_get):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "forecast_days": 8, "timezone": "Africa/Nairobi",
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,precipitation_sum,precipitation_probability_max"})
    d = fetch("https://api.open-meteo.com/v1/forecast?" + q)["daily"]
    out = []
    for i, day in enumerate(d["time"]):
        dd = date.fromisoformat(day)
        if dd > today and d["temperature_2m_mean"][i] is not None and d["relative_humidity_2m_mean"][i] is not None:
            out.append({"day": dd, "temp_c": d["temperature_2m_mean"][i], "rh": d["relative_humidity_2m_mean"][i],
                        "rain_mm": d["precipitation_sum"][i], "rain_prob": d["precipitation_probability_max"][i]})
    return out


def weatherapi(lat, lon, today, key, fetch=_get):
    q = urllib.parse.urlencode({"key": key, "q": f"{lat},{lon}", "days": 4, "aqi": "no", "alerts": "no"})
    days = fetch("https://api.weatherapi.com/v1/forecast.json?" + q)["forecast"]["forecastday"]
    out = []
    for f in days:
        dd = date.fromisoformat(f["date"])
        if dd > today:
            x = f["day"]
            out.append({"day": dd, "temp_c": x["avgtemp_c"], "rh": x["avghumidity"],
                        "rain_mm": x["totalprecip_mm"], "rain_prob": float(x.get("daily_chance_of_rain", 0))})
    return out


def openweather(lat, lon, today, key, fetch=_get):
    """5-day / 3-hour forecast folded into Kitale local days. Only complete days (8 slots) are used."""
    q = urllib.parse.urlencode({"lat": lat, "lon": lon, "units": "metric", "appid": key})
    slots = fetch("https://api.openweathermap.org/data/2.5/forecast?" + q)["list"]
    by = {}
    for s in slots:
        dd = datetime.fromtimestamp(s["dt"], TZ_EAT).date()
        by.setdefault(dd, []).append(s)
    out = []
    for dd in sorted(by):
        if dd <= today or len(by[dd]) < 8:
            continue
        s = by[dd]
        out.append({"day": dd, "temp_c": _mean([x["main"]["temp"] for x in s]), "rh": _mean([x["main"]["humidity"] for x in s]),
                    "rain_mm": sum((x.get("rain") or {}).get("3h", 0.0) for x in s),
                    "rain_prob": max(x.get("pop", 0.0) for x in s) * 100.0})
    return out


def providers(env=os.environ):
    """Preferred order for the engine: longest forecast first, then the commercially-usable ones."""
    p = [("open-meteo", lambda lat, lon, t: open_meteo(lat, lon, t))]
    if env.get("WEATHERAPI_KEY"):
        p.append(("weatherapi", lambda lat, lon, t: weatherapi(lat, lon, t, env["WEATHERAPI_KEY"])))
    if env.get("OPENWEATHER_API_KEY"):
        p.append(("openweather", lambda lat, lon, t: openweather(lat, lon, t, env["OPENWEATHER_API_KEY"])))
    return p


def best_forecast(lat, lon, today, env=os.environ, plist=None):
    """(provider name, days) from the first provider that returns tomorrow first with no gap, else (None, [])."""
    for name, fn in (plist or providers(env)):
        try:
            days = fn(lat, lon, today)
        except Exception:
            continue
        if days and days[0]["day"] == today + timedelta(days=1) and all(
                (days[i + 1]["day"] - days[i]["day"]).days == 1 for i in range(len(days) - 1)):
            return name, days
    return None, []


def cross_check(lat=KITALE[0], lon=KITALE[1], env=os.environ):
    today = datetime.now(TZ_EAT).date()
    rows = {}
    for name, fn in providers(env):
        try:
            rows[name] = {d["day"]: d for d in fn(lat, lon, today)}
        except Exception as e:
            rows[name] = {"error": str(e)[:80]}
    return today, rows


if __name__ == "__main__":
    today, rows = cross_check()
    print(f"Kitale, today (EAT) = {today}")
    for name, r in rows.items():
        if "error" in r:
            print(f"{name:12s} ERROR {r['error']}")
            continue
        print(f"{name:12s} {len(r)} days: " + " | ".join(
            f"{d:%d}: {v['temp_c']:.1f}C {v['rh']:.0f}% {v['rain_mm']:.1f}mm {v['rain_prob']:.0f}%" for d, v in sorted(r.items())))
