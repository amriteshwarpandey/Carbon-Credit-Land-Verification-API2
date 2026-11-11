"""Historical weather / soil moisture from NASA POWER (no API key required)."""
from datetime import date

import httpx

from app.config import settings

PARAMS = {
    "PRECTOTCORR": "precipitation_mm_day",
    "T2M": "temperature_c",
    "GWETROOT": "root_zone_soil_wetness",  # 0 (dry) .. 1 (saturated)
}


class WeatherError(Exception):
    pass


def _avg(values: dict) -> float | None:
    vals = [v for v in values.values() if v is not None and v > -900]  # -999 = missing
    return round(sum(vals) / len(vals), 3) if vals else None


def fetch_weather(lat: float, lon: float, start: date, end: date) -> dict:
    query = {
        "parameters": ",".join(PARAMS),
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        resp = httpx.get(settings.nasa_power_url, params=query, timeout=30)
        resp.raise_for_status()
        series = resp.json()["properties"]["parameter"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise WeatherError(f"NASA POWER request failed: {exc}") from exc

    summary = {label: _avg(series.get(code, {})) for code, label in PARAMS.items()}
    total_rain = sum(v for v in series.get("PRECTOTCORR", {}).values() if v is not None and v > -900)
    summary["total_precipitation_mm"] = round(total_rain, 2)
    return {
        "latitude": lat,
        "longitude": lon,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source": "NASA POWER",
        "summary": summary,
        "daily": {label: series.get(code, {}) for code, label in PARAMS.items()},
    }
