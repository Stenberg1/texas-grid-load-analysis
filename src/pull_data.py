"""Pull hourly ERCOT demand, generation by fuel (EIA), and temperature (Open-Meteo).

Usage:
    export EIA_KEY=...   (or put EIA_KEY=... in a .env file at the repo root)
    python src/pull_data.py

Writes:
    data/raw/ercot_demand.parquet      period, demand_mwh
    data/raw/ercot_generation.parquet  period, fueltype, generation_mwh
    data/raw/weather.parquet           period, city, temp_c
All timestamps are UTC.
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


def eia_paginate(url, extra_params):
    params = {
        "api_key": eia_key(),
        "frequency": "hourly",
        "data[0]": "value",
        "start": START,
        "end": END,
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


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    pull_demand()
    pull_generation()
    pull_weather()
