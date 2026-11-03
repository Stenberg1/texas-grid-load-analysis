"""Pull hourly ERCOT demand, generation by fuel (EIA), and temperature (Open-Meteo).

Usage:
    export EIA_KEY=...   (or put EIA_KEY=... in a .env file at the repo root)
    python src/pull_data.py

Writes:
    data/raw/ercot_demand.parquet      period, demand_mwh
    data/raw/ercot_generation.parquet  period, fueltype, generation_mwh
    data/raw/weather.parquet           period, city, temp_c
    data/raw/ercot_forecast.parquet    period, forecast_mwh   (ERCOT's day-ahead forecast, via EIA-930)
    data/raw/ercot_zone_load.parquet   period, zone, demand_mwh (8 ERCOT weather zones)
    data/raw/henry_hub.parquet         date, price_usd_mmbtu  (daily spot)
All timestamps are UTC.

Run everything, or name parts: python src/pull_data.py weather gas forecast zones
"""
import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
START, END = "2019-01-01T00", "2025-12-31T23"
PAGE = 5000

CITIES = {
    "Dallas": (32.78, -96.80),
    "Houston": (29.76, -95.37),
    "Austin": (30.27, -97.74),
    "San Antonio": (29.42, -98.49),
    "Corpus Christi": (27.80, -97.40),
    "Midland": (32.00, -102.08),
    "Lubbock": (33.58, -101.85),
    "Tyler": (32.35, -95.30),
}


def eia_key() -> str:
    key = os.environ.get("EIA_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("EIA_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("Set EIA_KEY in the environment or in .env")
    return key


def get_json(url, params, tries=5):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # network blips / rate limits
            if i == tries - 1:
                raise
            wait = 2 ** i * 3
            print(f"  retry {i + 1} after error: {e} (sleep {wait}s)")
            time.sleep(wait)


def eia_paginate(url, extra_params, frequency="hourly", start=START, end=END):
    params = {
        "api_key": eia_key(),
        "frequency": frequency,
        "data[0]": "value",
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": PAGE,
        **extra_params,
    }
    rows, offset = [], 0
    while True:
        params["offset"] = offset
        page = get_json(url, params)["response"]["data"]
        if not page:
            break
        rows.extend(page)
        offset += PAGE
        print(f"  {url.split('/')[-3]}: {len(rows):,} rows")
    return pd.DataFrame(rows)


def to_utc(period: pd.Series) -> pd.Series:
    # EIA hourly periods look like "2019-01-01T00" and are UTC.
    return pd.to_datetime(period, format="%Y-%m-%dT%H", utc=True)


def pull_demand():
    df = eia_paginate(
        "https://api.eia.gov/v2/electricity/rto/region-data/data/",
        {"facets[respondent][]": "ERCO", "facets[type][]": "D"},
    )
    out = pd.DataFrame({
        "period": to_utc(df["period"]),
        "demand_mwh": pd.to_numeric(df["value"], errors="coerce"),
    })
    out.to_parquet(RAW / "ercot_demand.parquet", index=False)
    print(f"demand: {len(out):,} rows, {out.period.min()} -> {out.period.max()}")


def pull_generation():
    df = eia_paginate(
        "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/",
        {"facets[respondent][]": "ERCO"},
    )
    out = pd.DataFrame({
        "period": to_utc(df["period"]),
        "fueltype": df["fueltype"],
        "generation_mwh": pd.to_numeric(df["value"], errors="coerce"),
    })
    out.to_parquet(RAW / "ercot_generation.parquet", index=False)
    print(f"generation: {len(out):,} rows, fuels={sorted(out.fueltype.unique())}")


def pull_weather():
    frames = []
    for city, (lat, lon) in CITIES.items():
        js = get_json(
            "https://archive-api.open-meteo.com/v1/archive",
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": START[:10],
                "end_date": END[:10],
                "hourly": "temperature_2m",
                "timezone": "UTC",
            },
        )
        frames.append(pd.DataFrame({
            "period": pd.to_datetime(js["hourly"]["time"], utc=True),
            "city": city,
            "temp_c": js["hourly"]["temperature_2m"],
        }))
        print(f"  weather {city}: {len(frames[-1]):,} rows")
        time.sleep(2)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(RAW / "weather.parquet", index=False)
    print(f"weather: {len(out):,} rows")


def pull_forecast():
    """ERCOT's own day-ahead demand forecast, as submitted to EIA (Form EIA-930, type DF)."""
    df = eia_paginate(
        "https://api.eia.gov/v2/electricity/rto/region-data/data/",
        {"facets[respondent][]": "ERCO", "facets[type][]": "DF"},
    )
    out = pd.DataFrame({
        "period": to_utc(df["period"]),
        "forecast_mwh": pd.to_numeric(df["value"], errors="coerce"),
    })
    out.to_parquet(RAW / "ercot_forecast.parquet", index=False)
    print(f"forecast: {len(out):,} rows, {out.period.min()} -> {out.period.max()}")


def pull_zone_load():
    """Hourly load for ERCOT's 8 weather zones (available from 2019-05-27)."""
    df = eia_paginate(
        "https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/data/",
        {"facets[parent][]": "ERCO"},
    )
    out = pd.DataFrame({
        "period": to_utc(df["period"]),
        "zone": df["subba"],
        "demand_mwh": pd.to_numeric(df["value"], errors="coerce"),
    })
    out.to_parquet(RAW / "ercot_zone_load.parquet", index=False)
    print(f"zone load: {len(out):,} rows, zones={sorted(out.zone.unique())}")


def pull_henry_hub():
    """Daily Henry Hub natural gas spot price, $/MMBtu (EIA series RNGWHHD)."""
    df = eia_paginate(
        "https://api.eia.gov/v2/natural-gas/pri/fut/data/",
        {"facets[series][]": "RNGWHHD"},
        frequency="daily", start=START[:10], end=END[:10],
    )
    out = pd.DataFrame({
        "date": pd.to_datetime(df["period"]).dt.date,
        "price_usd_mmbtu": pd.to_numeric(df["value"], errors="coerce"),
    })
    out.to_parquet(RAW / "henry_hub.parquet", index=False)
    print(f"henry hub: {len(out):,} days, {out.date.min()} -> {out.date.max()}")


PARTS = {
    "demand": pull_demand,
    "generation": pull_generation,
    "weather": pull_weather,
    "forecast": pull_forecast,
    "zones": pull_zone_load,
    "gas": pull_henry_hub,
}

if __name__ == "__main__":
    import sys
    RAW.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or PARTS:
        PARTS[name]()
