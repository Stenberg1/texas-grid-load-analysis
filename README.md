# Texas Grid Load Analysis

How has electricity demand on the Texas grid (ERCOT) changed from 2019 to 2025? How is solar reshaping it, what happened during Winter Storm Uri, does gas price move the generation mix, and how well can hourly load be forecast a day ahead compared with ERCOT's own forecast?

Built with Python, DuckDB SQL, scikit-learn/statsmodels and Plotly on seven years of hourly data (61,368 hours).

![Duck curve](charts/duck_curve.png)

## Key findings

| | |
|---|---|
| **Solar at midday** | Solar's share of generation from 11 am to 3 pm rose from **2.5% in 2019 to 32.9% in 2025**. Over the full day it went from 1.0% to 13.8%. |
| **Duck curve** | The average daily maximum 3-hour evening ramp in net load (demand minus wind and solar) grew **4.5×**, from **3.1 GW (2019) to 13.8 GW (2025)**. The single steepest ramp rose from 13.4 GW to 30.1 GW. |
| **Peak load** | Annual peak hourly load rose **14.8%**, from 74.5 GW (2019) to a record **85.5 GW (Aug 20 2024)**. Nearly all the growth came in 2022 (+8.7%) and 2023 (+7.0%). 2025 peaked at 83.6 GW. |
| **Fuel mix** | Coal fell from 20.4% to 13.0% of generation while total generation grew 27% (383 to 488 TWh). Gas stayed the largest source (41–47%). Wind plateaued near 24%. |
| **Gas price and fuel switching** | Controlling for net load, month and year, doubling the Henry Hub price cuts gas's share of fossil generation by only **1.6 points** (95% CI 0.8–2.3, from a 72% average). Switching has **faded**: 8.7 points per doubling in 2019, 0.9–2.9 points since 2022, as coal fell from 20.5% to 12.9% of generation and the remaining plants already run near full output. |
| **Winter Storm Uri** | Served demand peaked at **69.2 GW in the hour ending 8 pm on Feb 14 2021**. Over the next 54 hours generation fell **38.7% (68.0 to 41.7 GW)**: gas down 15.6 GW, wind 4.8 GW, coal 4.6 GW, nuclear 1.4 GW. EIA's demand fell in step to about 43 GW, because EIA reports *served* demand. **ERCOT's own day-ahead forecast ran up to 28.9 GW above served demand** (peaking at 76.8 GW) and **1,568 GWh above it over Feb 15–18**. That is an upper bound on load shed, since it also includes forecast error and conservation. EIA has no missing hours that week. |
| **Forecast vs ERCOT** | Our day-ahead model reached **2.94% MAPE** (RMSE 2,190 MWh) on 2024–2025, against **8.52%** for the same-hour-last-week baseline. **ERCOT's official forecast scored 2.31%** (RMSE 1,756 MWh) on the same hours. It wins overall, but our model beat it on **34% of days**. ERCOT's edge is largest on cold-snap holidays (MLK Day 2024: 4.8% vs our 16.3%). |

## Data sources

| Source | What | Range | Rows |
|---|---|---|---|
| [EIA Open Data API v2](https://www.eia.gov/opendata/), `electricity/rto/region-data` | Hourly ERCOT demand (`type=D`) | 2019-01-01 to 2025-12-31 (UTC) | 61,367 |
| EIA, `electricity/rto/region-data` | **ERCOT's own day-ahead demand forecast** (`type=DF`, as ERCOT files it on Form EIA-930) | same | 61,320 |
| EIA, `electricity/rto/fuel-type-data` | Hourly generation by fuel (NG, COL, NUC, WND, SUN, WAT, OTH, BAT, UES) | same | 449,006 |
| EIA, `electricity/rto/region-sub-ba-data` | Hourly load for ERCOT's 8 weather zones | 2019-05-27 onward | 462,405 |
| EIA, `natural-gas/pri/fut` (series `RNGWHHD`) | Daily Henry Hub natural gas spot price, $/MMBtu | 2019-01-02 to 2025-12-31 | 1,755 trading days |
| [Open-Meteo historical archive](https://open-meteo.com/en/docs/historical-weather-api) | Hourly 2 m temperature for 8 cities | same | 490,944 (61,368 per city) |

**Timestamps** are stored in UTC and converted to `America/Chicago` only for calendar fields. EIA hourly values are **hour-ending**: the row for 17:00 local covers 4–5 pm. A check on solar output confirms it: generation is centred on the hour ending 2 pm, which matches solar noon. Holidays are US federal holidays from the `holidays` package.

**Temperature** is a load-weighted average of 8 cities. Each city stands in for one ERCOT weather zone and is weighted by that zone's share of 2019–2023 load. Only training-period data sets the weights.

| City | Zone | Weight |
|---|---|---:|
| Dallas | North Central | 30.5% |
| Houston | Coast | 28.1% |
| Midland | Far West | 9.6% |
| San Antonio | South Central (split) | 8.3% |
| Austin | South Central (split) | 8.3% |
| Corpus Christi | Southern | 8.2% |
| Tyler | East | 3.8% |
| Lubbock | West | 3.1% |

The North zone (about 2.5% of load) has no city, so weights are renormalised over the other seven zones.

## Schema

```mermaid
erDiagram
    dim_calendar ||--o| fact_load : period
    dim_calendar ||--o| fact_forecast : period
    dim_calendar ||--o{ fact_generation : period
    dim_calendar ||--o{ fact_weather : period
    dim_calendar ||--o{ fact_zone_load : period
    dim_calendar }o--o| fact_gas_price : "local_date ASOF trade_date"
    dim_fuel ||--o{ fact_generation : fueltype
    dim_city ||--o{ fact_weather : city
    dim_city ||--|| dim_city_weight : city
    dim_calendar {
        timestamptz period PK
        timestamp local_ts
        date local_date
        int local_hour
        int day_of_week
        int month
        int year
        varchar season
        bool is_weekend
        bool is_holiday
    }
    dim_fuel {
        varchar fueltype PK
        varchar fuel_name
        bool is_renewable
        bool is_storage
    }
    dim_city {
        varchar city PK
        varchar zone
        double latitude
        double longitude
    }
    dim_city_weight {
        varchar city PK
        double weight
    }
    fact_load {
        timestamptz period FK
        double demand_mwh
        bool is_imputed
    }
    fact_forecast {
        timestamptz period FK
        bigint forecast_mwh
    }
    fact_generation {
        timestamptz period FK
        varchar fueltype FK
        bigint generation_mwh
        bool is_reclassified
    }
    fact_weather {
        timestamptz period FK
        varchar city FK
        double temp_c
    }
    fact_zone_load {
        timestamptz period FK
        varchar zone
        bigint demand_mwh
    }
    fact_gas_price {
        date trade_date
        double price_usd_mmbtu
    }
```

`model_hourly` is a wide table with one row per hour. It joins the calendar to demand, generation pivoted by fuel, weighted temperature, ERCOT's forecast and the Henry Hub price (an ASOF join carries Friday's price through the weekend). It adds window-function features: a 7-day rolling average, a 1-hour ramp, lags of 24 h and 168 h, and a 24-hour temperature lag.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "EIA_KEY=your_key_here" > .env          # free key from eia.gov/opendata
python src/pull_data.py                       # about 5 min, writes data/raw/*.parquet
python src/run_sql.py                         # builds data/grid.duckdb from sql/01..10
jupyter nbconvert --execute --inplace notebooks/*.ipynb   # analysis, model, charts, gas
```

| Path | Contents |
|---|---|
| `src/pull_data.py` | Paginated EIA pulls (5,000 rows per call) and Open-Meteo pull. `python src/pull_data.py gas forecast` reruns individual parts. |
| `sql/01_schema.sql` … `sql/10_forecast_compare.sql` | One question per file; the first line of each states it |
| `src/run_sql.py` | Runs the SQL files in order and prints row counts, quality checks and city weights |
| `notebooks/01_sql_analysis.ipynb` | Query results, spot checks, Uri numbers, EXPLAIN ANALYZE timings |
| `notebooks/02_model.ipynb` | Features, temperature validation, models, head-to-head comparison with ERCOT, error analysis |
| `notebooks/03_charts.ipynb` | Charts, exported to `charts/*.png` and `charts/*.html` |
| `notebooks/04_gas_prices.ipynb` | Gas price vs fuel mix: quintiles and a controlled regression |
| `src/build_notebooks.py` | Generates the notebooks from source |

## Data quality (sql/02_quality.sql)

| Check | Found | What was done |
|---|---|---|
| Missing demand hours | **1**: 2021-11-07 06:00 UTC, the hour clocks fell back for daylight saving | Time-weighted linear interpolation (33,926 MWh), flagged `is_imputed` |
| Missing generation hours | **24**: all of 2025-12-05 (UTC), every fuel | Left NULL; affects only fuel-mix totals for that day |
| Missing ERCOT forecast hours | **48**: Dec 5–7 2025 | Left NULL; dropped from every forecast comparison |
| Missing city-hour temperatures | 0 | — |
| Duplicate rows (demand, generation, forecast, gas price) | 0 | — |
| Demand or forecast < 0 or > 100,000 MWh; gas price ≤ 0 | 0 | — |
| Negative wind or solar | 0 | — |
| Gas misfiled as "Other" | **122 hours** on 5 days, Dec 2019 to Mar 2020: OTH jumps to 9–27 GW while NG drops to near 0 | OTH added back to NG for those hours, flagged `is_reclassified` (total MWh unchanged) |
| Smaller OTH bumps (1.5–4 GW) | 158 hours: 125 on 2024 summer and fall evenings, 32 on Dec 6–15 2025, 1 in 2023 | Left alone. The 2024 hours are most likely battery discharge before EIA split out `BAT` in Nov 2024. The Dec 2025 cluster follows the missing day of Dec 5 and is unexplained. |
| Weather zones don't sum to ERCOT total (more than 2% off) | **2,124 hours**: 9 before 2024, 249 in 2024, 1,866 in 2025 (mostly zones summing about 3.7% high, some hours missing zones) | Left alone. Zones are used only for temperature weights, which come from 2019–2023, where they match. |
| Uri week (Feb 13–20 2021) | No gaps or outliers, but demand is supply-capped | Kept as-is and reported as a finding |

**Bug fixed in review:** the Uri baseline originally averaged Jan 23–Feb 12. But Feb 10–12 were already near freezing, with demand of 54–64 GW, which inflated the "normal" baseline. It now uses Jan 20–Feb 9.

**Spot checks:** three hours (2021-02-15 06:00, 2023-08-10 23:00, 2025-06-01 18:00 UTC) were checked by hand. Their lag, ramp and solar columns match the raw parquet values exactly.

## Model results

Day-ahead forecast of hourly load. Train on 2019–2023, test on 2024–2025, split by time. Every feature is known a day ahead: calendar fields (hour, weekday, month, weekend, holiday), demand 24 h and 168 h earlier, temperature, cooling and heating degrees (base 18.3 °C), temperature squared, and the change in temperature from the same hour yesterday. All rows below use the same 17,496 test hours (the 48 with no ERCOT forecast are dropped).

| Model | RMSE (MWh) | MAPE (%) |
|---|---:|---:|
| Baseline: same hour last week | 6,481 | 8.52 |
| Reference: same hour yesterday | 3,500 | 4.51 |
| Linear regression (OLS, calendar dummies) | 3,604 | 5.56 |
| Gradient boosting, default settings, predicting load | 3,733 | 5.70 |
| **Gradient boosting, default settings, predicting change vs yesterday** | **2,190** | **2.94** |
| *ERCOT official day-ahead forecast* | *1,756* | *2.31* |

**Why the change-vs-yesterday target:** gradient boosting that predicts load directly loses to the naive "yesterday" forecast. Tree models cannot extrapolate, and 2024–25 load sits above most of the training range. Training the same default model on the change from yesterday, then adding back yesterday's load, fixes this. No hyperparameters were tuned.

**Which temperature (decided on a 2023 validation year, never the test set):**

| Temperature input | MAPE |
|---|---:|
| 4 cities, simple average | 2.89% |
| 8 cities, simple average | 3.11% |
| 8 cities, load-weighted (used) | 2.92% |

Adding the four smaller cities with equal weight makes the forecast worse. Load weighting brings it back to parity with the original four. The 0.03-point gap is within noise, and the weighted version covers West Texas load, so it is used.

**Against ERCOT:** ERCOT's forecast beats ours in every season. Ours beat it on 34% of days and 42% of hours.

| Season | Ours | ERCOT |
|---|---:|---:|
| Winter | 3.7% | 2.8% |
| Spring | 3.1% | 2.3% |
| Summer | 2.3% | 2.2% |
| Fall | 2.7% | 2.0% |

- **Summer is where we come closest:** 2.3% vs 2.2%, nearly a tie.
- **Bias:** ERCOT runs slightly high (+417 MWh on average); our model runs low (−1,033 MWh) as load keeps growing past its training range.
- **ERCOT's advantage despite worse weather data:** we feed the model observed temperature, while ERCOT had to use weather forecasts. ERCOT still wins, which points to its richer inputs (zonal models, many weather stations, operator adjustments).

**Where our model fails:**

| Breakdown | Our MAPE |
|---|---:|
| Winter | 3.7% |
| Spring | 3.1% |
| Fall | 2.7% |
| Summer | 2.3% |
| Overnight hours | about 2.5% |
| Hour ending 6 pm (worst hour) | 3.4% |
| Holidays | 4.31% |
| Other days | 2.89% |

The worst days:

1. **MLK Day 2024 (16.3%)**, a holiday during an Arctic cold snap.
2. **Jul 8 2024 (12.8%)**, when Hurricane Beryl knocked out power to about 2 million Houston customers.
3. **MLK Day 2025 (11.6%)**, another holiday in a cold snap.

![Model error by hour](charts/model_error_by_hour.png)

## Gas prices and the generation mix

Gas and coal compete for the load left after wind, solar and nuclear, so the outcome measure is gas / (gas + coal) by day. Uri (Feb 10–20 2021) is excluded because its price spike to $23.86 came with forced outages, not economic dispatch.

**Raw comparison (`sql/09_gas_price.sql`):** price quintiles are ranked *within each month*, so seasonality and coal retirements don't pose as a price effect. Gas share of fossil generation goes from 72.2% on the cheapest fifth of days to 71.5% on the most expensive.

**Controlled regression (`notebooks/04_gas_prices.ipynb`):** gas share of fossil is regressed on log(price), net load, net load squared, month and year, with Newey-West standard errors. The result: **−1.55 points per doubling of price** (95% CI −2.28 to −0.83).

**By year, the effect has faded:**

| Year | Points per doubling | Coal share (avg of days, Uri excluded) |
|---|---:|---:|
| 2019 | −8.7 | 20.5% |
| 2020 | −4.8 | 18.1% |
| 2021 | −3.8 (wide CI) | 19.2% |
| 2022 | −2.7 | 16.9% |
| 2023 | −0.9 | 13.9% |
| 2024 | −2.0 | 12.6% |
| 2025 | −2.9 | 12.9% |

With less coal left, and what remains already running near full output, there is little room to switch away from gas when it gets expensive.

![Gas switching](charts/gas_price_switching.png)

## Charts

Each has a static PNG and an interactive HTML version in `charts/`.

| Chart | Takeaway |
|---|---|
| [Load vs temperature](charts/load_vs_temperature.html) | Load is U-shaped in temperature, lowest near 16 °C |
| [Midday solar share](charts/midday_solar_share.html) | Rose from 2.5% to 32.9% of midday generation in six years |
| [Peak load by year](charts/peak_load_by_year.html) | Up 14.8% to an 85.5 GW record in 2024 |
| [Duck curve](charts/duck_curve.html) | Spring midday net load sinks to about 21 GW in 2025; the evening ramp steepens |
| [Winter Storm Uri](charts/uri_week.html) | Generation fell 39% from the peak; ERCOT's forecast ran up to 29 GW above served demand |
| [Gas price switching](charts/gas_price_switching.html) | Gas-to-coal switching has faded since 2019 |
| [Error by hour](charts/model_error_by_hour.html) / [by season](charts/model_error_by_season.html) | Our model vs the baseline vs ERCOT |

![Uri](charts/uri_week.png)

## Limitations

- **The ERCOT comparison favours us.** Our model uses observed temperature where a real day-ahead system has only a weather forecast; ERCOT had to use forecasts and still won. With forecast weather, our error would be higher.
- **The 24-hour lag is a simplification.** Treating the same hour yesterday as known a day ahead assumes the forecast is issued at the end of each hour. ERCOT publishes in the morning, before yesterday's evening hours are in.
- **ERCOT's forecast comes from EIA, not ERCOT directly.** It is ERCOT's own forecast as filed on Form EIA-930. ERCOT's public API (`np3-565-cd`, forecasts by model and weather zone) needs a registered account and was not used. It would allow comparison by weather zone and forecast model.
- **ERCOT-wide demand only.** The model forecasts total ERCOT load and does not use the zone data except for temperature weights. Eight cities stand in for statewide weather, and the North zone has no city.
- **Henry Hub is a national price.** Texas plants buy gas at Houston Ship Channel and Waha, and Waha in particular often trades far below Henry Hub. Coal prices are not included either.
- **EIA demand is served demand.** During load shed (Uri) it understates true demand, and those hours stay in the 2021 training data.
- **EIA data gaps and coding changes:** a missing generation day (2025-12-05), missing forecast days (Dec 5–7 2025), gas misfiled as OTH (fixed), zone totals that drift in 2024–25, and storage categories (BAT/UES) that only start in Nov 2024.
- **No electricity price data,** so the analysis cannot say what the ramps or Uri cost.

## SQL techniques used

- **Joins:**
  - LEFT JOIN against a generated hour spine for gap detection.
  - A self-join on weekday and hour for the Uri baseline.
  - Star-schema joins of facts to `dim_calendar`, `dim_fuel` and `dim_city`.
  - **ASOF JOIN** to carry the last Henry Hub price across weekends and holidays.
- **CTEs:** multi-step `WITH` pipelines in the model table, city weights, peak growth, fuel share, Uri and gas queries.
- **Window functions:**
  - `AVG … ROWS BETWEEN 167 PRECEDING` for the 7-day rolling average.
  - `LAG` for the 1 h ramp, 24 h and 168 h lags, the 3 h net-load ramp and year-over-year growth.
  - `RANK() OVER (PARTITION BY year)` for top peaks and ramps.
  - `NTILE(5) OVER (PARTITION BY year, month)` for gas price quintiles.
  - `LAST_VALUE/FIRST_VALUE … IGNORE NULLS` with named `WINDOW`s for interpolation.
  - `COUNT(*) OVER (PARTITION BY zone)` and `SUM … OVER ()` for city weights.
- **Conditional aggregation:** `SUM(CASE WHEN fueltype = 'SUN' …)` to pivot fuels into columns, and `AVG … FILTER (WHERE …)` for quintile comparisons.
- **Generated series:** `generate_series` over timestamps to build the calendar dimension.
- **Views:** `daily_peak`, `fuel_mix_yearly` and `net_load_hourly`.
- **Performance:** `EXPLAIN ANALYZE` on DuckDB 2.0, median of 5 runs. The 7-day rolling window over 61k rows took **4.5 ms**; the Uri weekday-and-hour self-join took **2.0 ms**.
