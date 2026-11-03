"""Pull ERCOT's day-ahead load forecasts (all models, all weather zones) from ERCOT's public API.

Report NP3-565-CD "Seven-Day Load Forecast by Model and Weather Zone". ERCOT re-posts it every
hour; for a true day-ahead forecast we keep, for each delivery day D, the posting made at
09:30 Central on D-1 (the last one before the 10:00 day-ahead market closes).

Needs in .env: ERCOT_SUBSCRIPTION_KEY, ERCOT_USERNAME, ERCOT_PASSWORD
(register at https://apiexplorer.ercot.com). Data is available from 2023-12-11.

Usage: python src/pull_ercot.py [start_date] [end_date]   (default 2024-01-01 2025-12-31)
Writes data/raw/ercot_forecast_models.parquet, one row per (delivery hour, model).
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "ercot_forecast_models.parquet"
CACHE = ROOT / "data" / "raw" / "ercot_cache"
URL = "https://api.ercot.com/api/public-reports/np3-565-cd/lf_by_model_weather_zone"
TOKEN_URL = ("https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
             "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token")
CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"
POSTED_HOUR = 9          # keep the posting made between 09:00 and 09:59 on the day before
PAUSE = 2.1              # seconds between calls (ERCOT allows ~30 requests/minute)


def env():
    vals = dict(l.split("=", 1) for l in (ROOT / ".env").read_text().splitlines() if "=" in l)
    for k in ["ERCOT_SUBSCRIPTION_KEY", "ERCOT_USERNAME", "ERCOT_PASSWORD"]:
        if k not in vals:
            raise SystemExit(f"{k} missing from .env")
    return vals


class Client:
    def __init__(self):
        self.env = env()
        self.token, self.token_time = None, 0

    def headers(self):
        if time.time() - self.token_time > 45 * 60:   # id tokens last 60 minutes
            r = requests.post(TOKEN_URL, timeout=60, data={
                "username": self.env["ERCOT_USERNAME"], "password": self.env["ERCOT_PASSWORD"],
                "grant_type": "password", "scope": f"openid {CLIENT_ID} offline_access",
                "client_id": CLIENT_ID, "response_type": "id_token"})
            r.raise_for_status()
            self.token, self.token_time = r.json()["id_token"], time.time()
        return {"Ocp-Apim-Subscription-Key": self.env["ERCOT_SUBSCRIPTION_KEY"],
                "Authorization": f"Bearer {self.token}"}

    def get(self, params, tries=6):
        for i in range(tries):
            try:
                r = requests.get(URL, params=params, headers=self.headers(), timeout=120)
                if r.status_code == 429:
                    raise RuntimeError("rate limited")
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if i == tries - 1:
                    raise
                wait = 10 * (i + 1)
                print(f"  retry {i + 1}: {e} (sleep {wait}s)", flush=True)
                time.sleep(wait)


def day_ahead(client, d: date) -> pd.DataFrame:
    prev = d - timedelta(days=1)
    js = client.get({
        "deliveryDateFrom": d.isoformat(), "deliveryDateTo": d.isoformat(),
        "postedDatetimeFrom": f"{prev.isoformat()}T{POSTED_HOUR:02d}:00:00",
        "postedDatetimeTo": f"{prev.isoformat()}T{POSTED_HOUR:02d}:59:59",
        "size": 5000,
    })
    cols = [f["name"] for f in js["fields"]]
    return pd.DataFrame(js["data"], columns=cols)


def to_period_utc(df: pd.DataFrame) -> pd.Series:
    """ERCOT hour-ending (Central prevailing time) -> UTC timestamp of the hour's end,
    matching EIA's hour-ending UTC periods.

    Localise the hour's START, then add one hour. On the fall-back day ERCOT lists hour-ending 2:00
    twice; both start at 01:00 local, which is ambiguous, and DSTFlag=True marks the second (CST)
    one. (Localising the END time instead maps both to 02:00 CST and collides.) On the spring-forward
    day ERCOT skips an hour, and 01:00 + 1 h lands correctly on 03:00 CDT."""
    he = df.hourEnding.str.split(":").str[0].astype(int)
    start = pd.to_datetime(df.deliveryDate) + pd.to_timedelta(he - 1, unit="h")
    start = start.dt.tz_localize("America/Chicago", ambiguous=~df.DSTFlag.astype(bool).values)
    return start.dt.tz_convert("UTC") + pd.Timedelta(hours=1)


def main():
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2024, 1, 1)
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2025, 12, 31)
    CACHE.mkdir(parents=True, exist_ok=True)
    client = Client()
    d, n = start, 0
    while d <= end:
        f = CACHE / f"{d.isoformat()}.parquet"
        if not f.exists():                      # resumable: skip days already pulled
            day_ahead(client, d).to_parquet(f, index=False)
            n += 1
            if n % 25 == 0:
                print(f"{d}: {n} days pulled", flush=True)
            time.sleep(PAUSE)
        d += timedelta(days=1)

    raw = pd.concat([pd.read_parquet(p) for p in sorted(CACHE.glob("*.parquet"))], ignore_index=True)
    out = pd.DataFrame({
        "period": to_period_utc(raw),
        "posted_ct": pd.to_datetime(raw.postedDatetime),
        "model": raw.model,
        "in_use": raw.inUseFlag.astype(bool),
        "coast": raw.coast, "east": raw.east, "far_west": raw.farWest, "north": raw.north,
        "north_central": raw.northCentral, "south_central": raw.southCentral,
        "southern": raw.southern, "west": raw.west,
        "system_total_mwh": raw.systemTotal,
    })
    out.to_parquet(OUT, index=False)
    print(f"ercot forecasts: {len(out):,} rows, {out.period.min()} -> {out.period.max()}, "
          f"models={sorted(out.model.unique())}")


if __name__ == "__main__":
    main()
