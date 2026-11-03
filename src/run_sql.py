"""Build data/grid.duckdb by running every sql/*.sql file in order.

Usage: python src/run_sql.py
"""
import os
from pathlib import Path

import duckdb
import holidays
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # SQL files use repo-relative parquet paths
DB = ROOT / "data" / "grid.duckdb"


def write_holidays():
    us = holidays.US(years=range(2018, 2027))
    df = pd.DataFrame({"holiday_date": list(us.keys()), "holiday_name": list(us.values())})
    df["holiday_date"] = pd.to_datetime(df["holiday_date"]).dt.date
    (ROOT / "data" / "clean").mkdir(parents=True, exist_ok=True)
    df.to_parquet(ROOT / "data" / "clean" / "us_holidays.parquet", index=False)


def main():
    write_holidays()
    con = duckdb.connect(str(DB))
    con.execute("SET TimeZone = 'UTC'")
    for f in sorted((ROOT / "sql").glob("*.sql")):
        print(f"running {f.name}")
        con.execute(f.read_text()).fetchall()

    print("\nRow counts")
    for t in ["raw_demand", "raw_generation", "raw_weather", "dim_fuel", "dim_calendar",
              "fact_load", "fact_generation", "fact_weather", "model_hourly"]:
        print(f"  {t:16s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchall()[0][0]:>9,}")

    print("\nParquet row counts")
    for p in ["ercot_demand", "ercot_generation", "weather"]:
        n = con.execute(f"SELECT COUNT(*) FROM 'data/raw/{p}.parquet'").fetchall()[0][0]
        print(f"  {p:16s} {n:>9,}")

    print("\nQuality summary")
    print(con.sql("SELECT * FROM qa_summary"))

    print("View checks")
    for v in ["daily_peak", "fuel_mix_yearly", "net_load_hourly"]:
        print(v)
        print(con.sql(f"SELECT * FROM {v} LIMIT 5"))
    con.close()


if __name__ == "__main__":
    main()
