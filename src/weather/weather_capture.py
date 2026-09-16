#!/usr/bin/env python3
"""Collect MET Norway Locationforecast point forecasts (not measured weather)."""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg2

API = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "ubecon.no oistein.aanensen@ubecon.no"
FIELDS = {"temp": "air_temperature", "wspd": "wind_speed",
          "wdir": "wind_from_direction", "rhum": "relative_humidity"}


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("API timestamp has no timezone")
    return result


def current_values(payload, now):
    props = payload["properties"]
    updated = timestamp(props["meta"]["updated_at"])
    if updated > now + timedelta(minutes=5) or now - updated > timedelta(hours=12):
        raise ValueError("Forecast issue time is stale or in the future")
    candidates = [(timestamp(p["time"]), p) for p in props["timeseries"]
                  if timestamp(p["time"]) <= now]
    if not candidates:
        raise ValueError("Forecast contains no current/past time step")
    valid, point = max(candidates, key=lambda item: item[0])
    if now - valid > timedelta(hours=2):
        raise ValueError("Forecast time step is stale")
    details = point["data"]["instant"]["details"]
    values = {abv: float(details[field]) for abv, field in FIELDS.items()}
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("Non-finite weather value")
    if not 0 <= values["rhum"] <= 100 or values["wspd"] < 0 or not 0 <= values["wdir"] <= 360:
        raise ValueError("Weather value outside physical range")
    return valid, updated, values


def fetch_forecast(latitude, longitude, altitude, cache_dir):
    params = {"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"}
    if altitude is not None:
        params["altitude"] = str(round(altitude))
    url = API + "?" + urlencode(params)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    cached = {}
    try:
        cached = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        pass
    if cached.get("expires", 0) > time.time():
        return cached["payload"]
    request = Request(url, headers={"User-Agent": os.getenv("WEATHER_USER_AGENT", USER_AGENT)})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
        expires = response.headers.get("Expires")
        expiry = parsedate_to_datetime(expires).timestamp() if expires else time.time() + 300
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"expires": expiry, "payload": payload}))
    temporary.replace(path)
    return payload


def get_weather(dsn=None, cache_dir=None):
    # Existing server cron works unchanged; local runs must explicitly select its DB.
    dsn = dsn or os.getenv("WEATHER_DATABASE_URL") or os.getenv("DAS_DATABASE_URL")
    connection = psycopg2.connect(dsn) if dsn else psycopg2.connect(
        dbname="sensnetdb", user="sensnetdbu", password="obs", host="10.147.20.10", port=5432)
    cache_dir = Path(cache_dir or os.getenv("WEATHER_CACHE_DIR", str(Path.home() / ".cache/sensnet-weather")))
    failed = 0
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("SELECT abv,type FROM weather_obs_types WHERE abv IN ('temp','wspd','wdir','rhum')")
            lookup = cursor.fetchall()
            types = dict(lookup)
            if set(types) != set(FIELDS) or len(lookup) != len(FIELDS):
                raise RuntimeError("Apply migration 005: missing or ambiguous weather variable definitions")
            cursor.execute("SELECT lid,latitude,longitude,altitude,name FROM weather_stations ORDER BY lid")
            stations = cursor.fetchall()
        for lid, lat, lon, altitude, name in stations:
            try:
                payload = fetch_forecast(lat, lon, altitude, cache_dir)
                collected = datetime.now(timezone.utc)
                valid, updated, values = current_values(payload, collected)
                inserted = 0
                with connection, connection.cursor() as cursor:
                    for abv, value in values.items():
                        cursor.execute("""
                            INSERT INTO weather_obs
                              (time,lid,type,value,source_time,forecast_updated_at,collected_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (lid,type,source_time,forecast_updated_at)
                              WHERE source_time IS NOT NULL DO NOTHING
                        """, (collected.astimezone(ZoneInfo("Europe/Oslo")).replace(tzinfo=None),
                              lid, types[abv], value, valid, updated, collected))
                        inserted += cursor.rowcount
                logging.info("%s (lid=%s): %s new values, forecast valid %s", name, lid, inserted, valid)
            except Exception:
                failed += 1
                logging.exception("Weather capture failed for %s (lid=%s)", name, lid)
    finally:
        connection.close()
    if failed:
        raise RuntimeError(f"Weather capture failed for {failed} station(s); successful stations committed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="PostgreSQL DSN; prefer WEATHER_DATABASE_URL for credentials")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    get_weather(args.dsn, args.cache_dir)
