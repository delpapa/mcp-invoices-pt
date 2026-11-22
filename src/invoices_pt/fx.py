"""ECB euro reference rates, cached per currency and year."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import tempfile
import time
import urllib.request

URL = ("https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A"
       "?startPeriod={start}&endPeriod={end}&format=csvdata")


def _fetch(currency: str, year: int) -> dict[str, float]:
    start = dt.date(year, 1, 1) - dt.timedelta(days=10)   # so 1-2 January can fall back to December
    url = URL.format(cur=currency, start=start.isoformat(), end=dt.date(year, 12, 31).isoformat())
    with urllib.request.urlopen(url, timeout=30) as resp:
        rows = csv.DictReader(io.StringIO(resp.read().decode()))
        return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows if r.get("OBS_VALUE")}


def rate(currency: str, day: dt.date, cache_dir: str) -> float:
    """Units of `currency` per 1 EUR on `day`, or on the last ECB publication day before it."""
    currency = currency.upper()
    if currency == "EUR":
        return 1.0
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"ecb_{currency}_{day.year}.json")
    try:
        with open(path) as cache:
            cached = json.load(cache)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        cached = {}
    # Older cache files are plain date-to-rate mappings.
    rates = cached.get("rates", cached)
    fetched_at = cached.get("fetched_at", 0)
    now = time.time()
    last_weekday = day - dt.timedelta(days=max(day.weekday() - 4, 0))
    fetched_day = dt.datetime.fromtimestamp(fetched_at, dt.UTC).date()
    # A later snapshot already covers this historical date. For an unpublished
    # rate today, recheck hourly so a later ECB publication can replace the fallback.
    needs_update = not fetched_at or (last_weekday >= fetched_day and now - fetched_at >= 3600)
    if last_weekday.isoformat() > max(rates, default="") and needs_update:
        rates = _fetch(currency, day.year)
        # Readers see either complete snapshot, even when a write fails partway through.
        with tempfile.TemporaryDirectory(dir=cache_dir) as staging:
            snapshot = os.path.join(staging, "rates.json")
            with open(snapshot, "w") as temp:
                json.dump({"fetched_at": now, "rates": rates}, temp)
            os.replace(snapshot, path)
    for back in range(8):
        key = (day - dt.timedelta(days=back)).isoformat()
        if key in rates:
            return rates[key]
    raise LookupError(f"no ECB {currency} rate on or before {day}")
