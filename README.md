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
| **Weather-adjusted growth** | Is the rise growth or just hotter summers? At identical weather and calendar, ERCOT load grew **26% from 2019 to 2025 (about 3.9% a year)**, almost exactly the raw 27%. Weather explains essentially none of it. Summer-afternoon load at identical weather grew 18%, *more* than the raw peak (+12% by 2025): the milder summers of 2024–25 hid the growth. The fastest-growing zones from 2020 to 2023 were **Far West (Permian Basin) +58%** and North +46%, against about 10–11% for the Dallas and Houston zones. |
| **Fuel mix** | Coal fell from 20.4% to 13.0% of generation while total generation grew 27% (383 to 488 TWh). Gas stayed the largest source (41–47%). Wind plateaued near 24%. |
| **Gas price and fuel switching** | Controlling for net load, month and year, doubling the Henry Hub price cuts gas's share of fossil generation by only **1.6 points** (95% CI 0.8–2.3, from a 72% average). Switching has **faded**: 8.7 points per doubling in 2019, 0.9–2.9 points since 2022, as coal fell from 20.5% to 12.9% of generation and the remaining plants already run near full output. |
| **Winter Storm Uri** | Served demand peaked at **69.2 GW in the hour ending 8 pm on Feb 14 2021**. Over the next 54 hours generation fell **38.7% (68.0 to 41.7 GW)**: gas down 15.6 GW, wind 4.8 GW, coal 4.6 GW, nuclear 1.4 GW. EIA's demand fell in step to about 43 GW, because EIA reports *served* demand. **ERCOT's own day-ahead forecast ran up to 28.9 GW above served demand** (peaking at 76.8 GW) and **1,568 GWh above it over Feb 15–18**. That is an upper bound on load shed, since it also includes forecast error and conservation. EIA has no missing hours that week. |
| **Forecast vs ERCOT** | Our day-ahead model reached **2.94% MAPE** (RMSE 2,190 MWh) on 2024–2025, against **8.52%** for the same-hour-last-week baseline. **ERCOT's official forecast scored 2.31%** (RMSE 1,756 MWh) on the same hours. It wins overall, but our model beat it on **34% of days**. ERCOT's edge is largest on cold-snap holidays (MLK Day 2024: 4.8% vs our 16.3%). The result holds on ERCOT's own API: its 9:30 am posting the day before scored **2.38%**. |
| **What drives the model** | Yesterday's load matters most, then Dallas and Austin temperature, then day of week. The four added cities (Corpus Christi, Tyler, Midland, Lubbock) *together* matter less than Dallas alone, and a model with all 8 cities as separate inputs scores the same 2.94%. |
| **Biggest misses** | 9 of the 10 worst days are under-forecasts, and 6 involve a holiday or the day after one, usually during cold weather. The holiday flag barely registers in the model (about 10 holidays a year to learn from), and that is the clearest weakness. |

## Data sources

| Source | What | Range | Rows |
|---|---|---|---|
| [EIA Open Data API v2](https://www.eia.gov/opendata/), `electricity/rto/region-data` | Hourly ERCOT demand (`type=D`) | 2019-01-01 to 2025-12-31 (UTC) | 61,367 |
| EIA, `electricity/rto/region-data` | **ERCOT's own day-ahead demand forecast** (`type=DF`, as ERCOT files it on Form EIA-930) | same | 61,320 |
| [ERCOT public API](https://apiexplorer.ercot.com), report `NP3-565-CD` | ERCOT's 7-day load forecast by model and weather zone. We keep the **09:30 posting the day before** each delivery day (before the 10:00 day-ahead market), all 8 forecast models | 2024-01-01 to 2025-12-31 | 135,217 |
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
# ERCOT API (needs a free account at apiexplorer.ercot.com): add ERCOT_SUBSCRIPTION_KEY,
# ERCOT_USERNAME and ERCOT_PASSWORD to .env, then:
python src/pull_ercot.py                      # about 25 min (rate-limited), resumable
python src/run_sql.py                         # builds data/grid.duckdb from sql/01..10
jupyter nbconvert --execute --inplace notebooks/*.ipynb   # run in order 01 to 05
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
| `notebooks/05_drivers_and_misses.ipynb` | Weather-adjusted growth, per-city feature importance, the 10 biggest misses |
| `src/pull_ercot.py` | ERCOT API pull: token login, one request per delivery day, cached per day so it can resume |
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
| ERCOT API, daylight saving | ERCOT lists "hour ending 2:00" twice on fall-back days, with a DST flag on the second | Converted from each hour's start time, so the two hours land on different UTC hours. Result: 17,544 hours, no duplicates, exactly one in-use model per hour. |

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

### Check: ERCOT's own API

The headline compares against the EIA copy of ERCOT's forecast, because it covers all seven years with one consistent source. As a check, `src/pull_ercot.py` pulls ERCOT's forecast directly from ERCOT's API: the 09:30 Central posting on the day before each delivery day, the last one before the day-ahead market closes, for every forecast model.

| Forecast (same 17,489 test hours) | RMSE (MWh) | MAPE (%) |
|---|---:|---:|
| ERCOT day-ahead forecast, EIA-930 copy (headline) | 1,757 | 2.31 |
| ERCOT 9:30 am posting, in-use model (ERCOT API) | 1,810 | 2.38 |
| Ours | 2,190 | 2.94 |
| Baseline: same hour last week | 6,482 | 8.53 |

**The conclusion holds on both sources.** The EIA copy scores slightly better and differs by about 465 MWh per hour on average, consistent with it being a later posting.

**ERCOT's own forecast models (API, 2024–25):**

| Model | MAPE | Share of hours in use |
|---|---:|---:|
| X (from Aug 2024 only) | 2.08% | 10% |
| M | 2.25% | 5% |
| The in-use pick | 2.39% | — |
| E3 | 2.58% | 21% |
| E | 2.60% | 28% |
| A3 | 2.62% | 0.1% |
| A6 | 2.71% | — |
| E2 | 2.72% | 18% |
| E1 | 2.77% | 17% |

With hindsight, ERCOT's choice of model each day did worse than always using M. To be fair to ERCOT, the choice is made without hindsight.

**By weather zone,** the in-use forecast misses big zones by 3.6–4.0% and small ones by much more: East 5.7%, North 6.4%, West 9.6%.

**A blend, with a caveat.** A weighted average of 35% ours and 65% ERCOT (weight fit on 2024, scored on 2025) reaches 1.94% MAPE in 2025, against 2.53% for ERCOT alone. **This is not a fair test.** Our model sees actual temperatures and yesterday's late-evening load, and ERCOT had neither at 9:30 am, so most of the gain is that hindsight leaking in. It shows our model carries *timing-advantaged* information, not that it would improve ERCOT's operational forecast.

### What drives the model

The same model was retrained with each of the 8 cities' temperatures as separate inputs (test MAPE 2.94%, identical to the weighted-average version). Each group of inputs was then shuffled on the test set to see how much accuracy falls (grouped permutation importance, 5 shuffles each).

| Input | MAPE rise when shuffled (pts) |
|---|---:|
| Demand 24 h earlier | 2.34 |
| Dallas temperature | 0.89 |
| Austin temperature | 0.64 |
| Day of week | 0.62 |
| Hour of day | 0.35 |
| Houston / Corpus Christi temperature | 0.31 each |
| San Antonio temperature | 0.23 |
| Tyler temperature | 0.16 |
| Midland temperature | 0.10 |
| Month | 0.07 |
| Lubbock temperature | 0.07 |
| Demand 1 week earlier | 0.07 |
| Holiday / weekend flags | 0.01 |

The four added cities sum to 0.64 points, less than Dallas alone, which answers whether they were worth adding: they are used, but they don't improve accuracy. City temperatures move together, so correlated cities split the credit. Houston's modest score means "adds little that Dallas, Austin and Corpus Christi don't already carry", not "Houston weather doesn't matter".

![Feature importance](charts/feature_importance.png)

### The 10 biggest misses (test set, by daily MAPE)

The context column is generated from the data (holidays, the day after a holiday, freezing or extreme heat, temperature swings from the day before), except Hurricane Beryl.

| Date | Day | Ours | ERCOT | Worst hour (error) | Context |
|---|---|---:|---:|---|---|
| 2024-01-15 | Mon | 16.3% | 4.8% | 8 am (−23.0 GW) | MLK Day, freezing (low −7 °C) |
| 2024-07-08 | Mon | 12.8% | 15.4% | 5 pm (+12.6 GW) | Hurricane Beryl landfall near Houston; about 2.2 million customers lost power |
| 2025-01-20 | Mon | 11.6% | 2.8% | 6 pm (−12.1 GW) | MLK Day, freezing (low −4 °C) |
| 2024-01-16 | Tue | 10.9% | 4.6% | 5 am (−15.7 GW) | Day after MLK Day (the model anchors on holiday-level load), freezing (low −9 °C) |
| 2025-03-08 | Sat | 10.1% | 2.3% | 5 pm (−9.9 GW) | No clear driver in our data |
| 2025-01-02 | Thu | 10.0% | 1.8% | 9 am (−6.7 GW) | Day after New Year's Day |
| 2025-11-29 | Sat | 9.1% | 1.0% | 5 pm (−5.8 GW) | Two days after Thanksgiving |
| 2024-01-14 | Sun | 8.6% | 3.6% | 6 pm (−12.0 GW) | Freezing (low −5 °C), a 14 °C swing from the day before |
| 2025-02-14 | Fri | 8.4% | 4.7% | 3 pm (−7.3 GW) | No clear driver in our data |
| 2025-11-11 | Tue | 8.4% | 5.7% | 9 am (−6.6 GW) | Veterans Day |

**Patterns in the misses:**
- **Holidays break the model's anchor.** It leans on yesterday's load, so a holiday, or the day after one, throws it off, and the holiday flag carries almost no weight (0.01 points above).
- **Cold snaps cause the biggest misses.** Load rises steeply in the cold, and the model under-forecasts it.
- **Beryl is the one day ERCOT missed worse than we did.** Outages took load away from both forecasts.
- **ERCOT handles holidays far better,** with 1.0–4.8% on the holiday-related days against our 8–16%.

**Where our model fails, by group:**

| Breakdown | Our MAPE |
|---|---:|
| Winter | 3.7% |
| Spring | 3.1% |
| Fall | 2.7% |
| Summer | 2.3% |
| Overnight | about 2.5% |
| Hour ending 6 pm (worst hour) | 3.4% |
| Holidays | 4.31% |
| Other days | 2.89% |

## Weather-adjusted demand growth

Peak load rose 15% to the 2024 record. To separate growth from weather, `notebooks/05_drivers_and_misses.ipynb` fits log(hourly load) on:
- **Temperature:** cooling and heating degrees and their squares, each with its own effect by hour of day.
- **Calendar:** hour, weekday, month and holidays.
- **A year effect:** the change in load at identical weather and calendar.

Uri and the Beryl outage period are excluded, since load there was lost to outages. R² is 0.96.

| Year | Actual avg load | Weather-adjusted, all hours | Weather-adjusted, summer afternoons | Actual annual peak | Summer cooling degrees |
|---|---:|---:|---:|---:|---:|
| 2019 | — | — | — | — | 10.1 |
| 2020 | −1.0% | +0.3% | −1.4% | −0.5% | 9.5 |
| 2021 | +1.8% | +4.4% | +4.7% | −1.4% | 8.9 |
| 2022 | +12.2% | +9.3% | +6.4% | +7.1% | 10.7 |
| 2023 | +16.5% | +14.9% | +11.7% | +14.6% | 11.7 |
| 2024 | +20.2% | +20.7% | +15.2% | +14.8% | 9.9 |
| 2025 | +27.2% | +26.0% | +18.4% | +12.2% | 9.8 |

All changes are relative to 2019.

- **The growth is structural, not weather.** At identical weather, load is 26% higher than in 2019, about 3.9% a year.
- **Milder summers hid it.** Summers in 2024–25 were milder than 2023, with cooling degrees back near the 2019 level. That's why the *raw* peak stalled even though summer-afternoon load at identical weather kept climbing.
- **The fastest growth is in West Texas.** Comparing full years 2020 to 2023 by zone: Far West, the Permian Basin oil field, rose 58%; North rose 46%; Coast and North Central rose about 10–11%. That pattern is consistent with oil-field electrification and large new industrial loads such as crypto mining and data centers, though this data can't separate them.
- **EIA load is net of rooftop solar,** which grows over time, so growth in underlying consumption is if anything understated.

![Weather-adjusted growth](charts/weather_adjusted_growth.png)

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
| [Weather-adjusted growth](charts/weather_adjusted_growth.html) | At identical weather, load grew 26% from 2019 to 2025 |
| [Duck curve](charts/duck_curve.html) | Spring midday net load sinks to about 21 GW in 2025; the evening ramp steepens |
| [Winter Storm Uri](charts/uri_week.html) | Generation fell 39% from the peak; ERCOT's forecast ran up to 29 GW above served demand |
| [Gas price switching](charts/gas_price_switching.html) | Gas-to-coal switching has faded since 2019 |
| [What drives the model](charts/feature_importance.html) | Yesterday's load, then Dallas and Austin temperature |
| [Error by season](charts/model_error_by_season.html) | Our model vs the baseline vs ERCOT |

![Uri](charts/uri_week.png)

## Limitations

- **The ERCOT comparison favours us.** Our model uses observed temperature where a real day-ahead system has only a weather forecast; ERCOT had to use forecasts and still won. With forecast weather, our error would be higher.
- **The 24-hour lag is a simplification.** Treating the same hour yesterday as known a day ahead assumes the forecast is issued at the end of each hour. ERCOT publishes in the morning, before yesterday's evening hours are in.
- **Two sources for ERCOT's forecast.** The headline uses the EIA-930 copy (all 7 years; its posting time is not documented). ERCOT's own API (2024–25 only, needs a registered account) is used as a check on a documented 9:30 am posting. The two agree within 0.07 points.
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
- **PIVOT / UNPIVOT:** `UNPIVOT` turns ERCOT's 8 zone columns into rows to join with zone load; `PIVOT` puts the 8 city temperatures into columns for the per-city model.
- **Views:** `daily_peak`, `fuel_mix_yearly` and `net_load_hourly`.
- **Performance:** `EXPLAIN ANALYZE` on DuckDB 2.0, median of 5 runs. The 7-day rolling window over 61k rows took **4.5 ms**; the Uri weekday-and-hour self-join took **2.0 ms**.
