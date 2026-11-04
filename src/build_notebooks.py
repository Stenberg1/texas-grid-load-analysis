"""Builds the project notebooks from cell lists. Usage: python src/build_notebooks.py notebooks"""
import sys
from pathlib import Path

import nbformat as nbf

NB = Path(sys.argv[1])

SETUP = '''import os, sys
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "src"))
import duckdb, numpy as np, pandas as pd
pd.set_option("display.width", 160); pd.set_option("display.max_columns", 30)
con = duckdb.connect("data/grid.duckdb", read_only=True)
con.execute("SET TimeZone = 'UTC'")
q = lambda sql: con.execute(sql).df()'''


def build(name, cells):
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    for kind, src in cells:
        nb.cells.append(nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src))
    nbf.write(nb, NB / name)


def sql_cell(path):
    return f'print(open("{path}").read().splitlines()[0])'


# ---------------------------------------------------------------- 01 SQL analysis
build("01_sql_analysis.ipynb", [
    ("md", "# 01 · SQL analysis\nReads the tables and views built by `python src/run_sql.py` (which runs `sql/01_schema.sql` … `sql/08_views.sql` against `data/grid.duckdb`)."),
    ("code", SETUP),
    ("md", "## Row counts"),
    ("code", '''tables = ["raw_demand", "raw_generation", "raw_weather", "dim_fuel", "dim_calendar",
          "fact_load", "fact_generation", "fact_weather", "model_hourly"]
pd.DataFrame({"table": tables, "rows": [q(f"SELECT COUNT(*) n FROM {t}").n[0] for t in tables]})'''),
    ("md", "## Data quality (sql/02_quality.sql)"),
    ("code", 'q("SELECT * FROM qa_summary")'),
    ("code", 'q("SELECT * FROM qa_missing_demand")'),
    ("code", '''q("""SELECT CAST(local_ts AS DATE) AS local_date, COUNT(*) AS hours
     FROM qa_missing_generation GROUP BY 1""")'''),
    ("code", '''q("""SELECT CAST(period AS DATE) AS utc_date, COUNT(*) AS hours, ROUND(AVG(value)) AS avg_oth_mwh
     FROM qa_outliers WHERE issue LIKE 'OTH spike%' GROUP BY 1 ORDER BY 1""")'''),
    ("md", "## Window functions (sql/04_windows.sql)"),
    ("code", 'q("SELECT * FROM peak_growth_yearly")'),
    ("code", 'q("SELECT year, local_ts, demand_mwh, ROUND(avg_temp_c,1) AS avg_temp_c FROM top_peaks_yearly WHERE peak_rank <= 3")'),
    ("code", '''# Spot check: lag and ramp columns vs raw data for three hours
q("""SELECT period, demand_mwh, demand_lag_24, demand_lag_168, ramp_1h, demand_7d_avg
     FROM model_hourly
     WHERE period IN ('2021-02-15 06:00+00', '2023-08-10 23:00+00', '2025-06-01 18:00+00')""")'''),
    ("code", '''q("""SELECT period, demand_mwh FROM raw_demand
     WHERE period IN ('2023-08-10 22:00+00','2023-08-09 23:00+00','2023-08-03 23:00+00','2023-08-10 23:00+00')
     ORDER BY period""")'''),
    ("md", "## Fuel mix and solar (sql/05_fuel_mix.sql)"),
    ("code", 'q("SELECT * FROM fuel_share_yearly")'),
    ("code", 'q("SELECT * FROM midday_solar_share")'),
    ("md", "## Net load and the duck curve (sql/06_net_load.sql)"),
    ("code", 'q("SELECT * FROM evening_ramp_yearly")'),
    ("code", 'q("SELECT * FROM top_evening_ramps WHERE ramp_rank <= 2")'),
    ("md", "## Winter Storm Uri (sql/07_uri.sql)"),
    ("code", 'q("SELECT * FROM uri_daily")'),
    ("code", '''u = q("SELECT * FROM uri_hourly")
peak = u.loc[u.demand_mwh.idxmax()]
after = u[(u.local_ts > peak.local_ts) & (u.local_date <= pd.Timestamp('2021-02-18'))]  # outage window Feb 15-18
trough = after.loc[after.total_gen_mwh.idxmin()]
uri = {
    "peak demand hour (local)": peak.local_ts,
    "peak served demand MWh": peak.demand_mwh,
    "total generation at peak MWh": peak.total_gen_mwh,
    "lowest generation during outages (local)": trough.local_ts,
    "lowest generation MWh": trough.total_gen_mwh,
    "generation drop MWh": peak.total_gen_mwh - trough.total_gen_mwh,
    "generation drop %": round(100 * (peak.total_gen_mwh - trough.total_gen_mwh) / peak.total_gen_mwh, 1),
    "gas at peak MWh": peak.gas_mwh, "gas at trough MWh": trough.gas_mwh,
    "coal at peak MWh": peak.coal_mwh, "coal at trough MWh": trough.coal_mwh,
    "nuclear at peak MWh": peak.nuclear_mwh, "nuclear at trough MWh": trough.nuclear_mwh,
    "wind at peak MWh": peak.wind_mwh, "wind at trough MWh": trough.wind_mwh,
    "temp at trough C": round(trough.avg_temp_c, 1),
    "storm-week wind vs baseline %": round(100 * (u.wind_mwh.mean() / u.base_wind.mean() - 1), 1),
    "missing hours in storm week": int(u.demand_mwh.isna().sum() + u.total_gen_mwh.isna().sum()),
}
outage = u[(u.local_date >= pd.Timestamp("2021-02-15")) & (u.local_date <= pd.Timestamp("2021-02-18"))]
uri.update({
    "ERCOT forecast peak during outages MWh": outage.ercot_forecast_mwh.max(),
    "max hourly forecast minus served MWh": outage.forecast_minus_served.max(),
    "hour of max gap (local)": outage.loc[outage.forecast_minus_served.idxmax(), "local_ts"],
    "forecast minus served, Feb 15-18 total GWh": round(outage.forecast_minus_served.sum() / 1000),
})
pd.Series(uri, dtype=object)'''),
    ("md", "## Views and performance (sql/08_views.sql)"),
    ("code", 'for v in ["daily_peak", "fuel_mix_yearly", "net_load_hourly"]:\n    display(q(f"SELECT * FROM {v} LIMIT 5"))'),
    ("code", '''import re
def explain_ms(sql):
    plan = con.execute("EXPLAIN ANALYZE " + sql).fetchall()[0][1]
    return float(re.search(r"Total Time: ([0-9.]+)s", plan).group(1)) * 1000

rolling = """SELECT period, AVG(demand_mwh) OVER (ORDER BY period ROWS BETWEEN 167 PRECEDING AND CURRENT ROW)
             FROM model_hourly"""
uri_self_join = open("sql/07_uri.sql").read().split("CREATE OR REPLACE TABLE uri_hourly AS")[1].split(";")[0]
timings = pd.DataFrame({
    "query": ["rolling 7-day average (61k rows)", "Uri baseline self-join"],
    "median_ms_of_5": [np.median([explain_ms(s) for _ in range(5)]) for s in (rolling, uri_self_join)],
}).round(1)
timings'''),
])

# ---------------------------------------------------------------- 02 model
build("02_model.ipynb", [
    ("md", """# 02 · Day-ahead load forecast
**Forecast definition:** predict each hour's ERCOT demand one day ahead. Every feature must be known a day earlier: calendar fields, demand lags of 24 h and 168 h, and temperature.
**Temperature:** load-weighted average of 8 Texas cities (weights = each ERCOT weather zone's share of 2019–2023 load).
**Limitation:** this is the hindsight version. It uses observed temperature and yesterday's full load, neither of which a forecaster has at ERCOT's 9:30 am posting. Notebook 06 rebuilds the forecast with only what was known at 9:30 am, and that is the headline result.
**Split:** train 2019–2023, test 2024–2025 (by time, never random). The temperature definition is chosen on a 2023 validation year, never on the test set."""),
    ("code", SETUP),
    ("code", '''df = q("SELECT * FROM model_hourly ORDER BY period")
df = df.iloc[168:].copy()          # first 168 rows have no lag_168
df["cooling_degree"] = (df.avg_temp_c - 18.3).clip(lower=0)
df["heating_degree"] = (18.3 - df.avg_temp_c).clip(lower=0)
df["temp_sq"] = df.avg_temp_c ** 2
df["temp_delta_24"] = df.avg_temp_c - df.temp_lag_24
df["is_weekend"] = df.is_weekend.astype(int)
df["is_holiday"] = df.is_holiday.astype(int)
print(len(df), "rows;", df[["demand_mwh", "demand_lag_24", "demand_lag_168", "avg_temp_c"]].isna().sum().sum(), "nulls in key columns")
train = df[df.period.dt.year <= 2023].copy()
test = df[df.period.dt.year >= 2024].copy()
print(f"train {len(train):,} rows ({train.period.min():%Y-%m-%d} to {train.period.max():%Y-%m-%d})")
print(f"test  {len(test):,} rows ({test.period.min():%Y-%m-%d} to {test.period.max():%Y-%m-%d})")'''),
    ("md", "## Features"),
    ("code", '''TEMP = ["avg_temp_c", "cooling_degree", "heating_degree", "temp_sq"]
FLAGS = ["is_weekend", "is_holiday"]
LAGS = ["demand_lag_24", "demand_lag_168"]
CAL = ["local_hour", "day_of_week", "month"]
BASE_FEATURES = TEMP + FLAGS + LAGS + CAL
# The change-vs-yesterday model gets NO load-level inputs: yesterday's load is only the anchor that the
# predicted change is added to. With levels as inputs, the model learned 2019-23 mean reversion ("high load
# days are followed by drops") and, with load now permanently higher, under-forecast 2024-25 by ~1,000 MWh.
# Dropping them was chosen on the 2023 validation year (MAPE 2.92% -> 2.65%), not on the test set.
FINAL_FEATURES = TEMP + FLAGS + CAL + ["temp_delta_24"]'''),
    ("md", "## Which temperature? (validation: train 2019–2022, validate 2023)"),
    ("code", '''from sklearn.ensemble import HistGradientBoostingRegressor
def temp_features(d, col):
    d = d.copy()
    d["avg_temp_c"] = d[col]
    d["cooling_degree"] = (d.avg_temp_c - 18.3).clip(lower=0)
    d["heating_degree"] = (18.3 - d.avg_temp_c).clip(lower=0)
    d["temp_sq"] = d.avg_temp_c ** 2
    d["temp_delta_24"] = d.avg_temp_c - d[col].shift(24)
    return d.dropna(subset=["temp_delta_24"])

rows = {}
for col, label in [("temp_4city_c", "4 cities, simple average"),
                   ("temp_8city_simple_c", "8 cities, simple average"),
                   ("avg_temp_c", "8 cities, load-weighted (used)")]:
    d = temp_features(df, col)
    tr, va = d[d.period.dt.year <= 2022], d[d.period.dt.year == 2023]
    m = HistGradientBoostingRegressor(random_state=0).fit(tr[FINAL_FEATURES], tr.demand_mwh - tr.demand_lag_24)
    e = va.demand_mwh - (va.demand_lag_24 + m.predict(va[FINAL_FEATURES]))
    rows[label] = {"RMSE (MWh)": round(np.sqrt((e ** 2).mean())), "MAPE (%)": round(100 * (e.abs() / va.demand_mwh).mean(), 2)}
pd.DataFrame(rows).T'''),
    ("md", "## Models"),
    ("code", '''import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingRegressor

def metrics(y, p):
    e = y - p
    return {"RMSE (MWh)": np.sqrt((e ** 2).mean()), "MAPE (%)": 100 * (e.abs() / y).mean()}

# Compare every model on the same hours: drop the 48 test hours with no ERCOT forecast (Dec 5-7 2025)
n_before = len(test)
test = test[test.ercot_forecast_mwh.notna()].copy()
print(f"test rows used: {len(test):,} (dropped {n_before - len(test)} with no ERCOT forecast)")

preds = {}
# 1. Baseline: same hour one week earlier
preds["Baseline: same hour last week"] = test.demand_lag_168
# Extra reference: same hour yesterday
preds["Reference: same hour yesterday"] = test.demand_lag_24

# 2. Linear regression. Calendar fields as dummies. avg_temp_c is dropped because
#    cooling_degree - heating_degree = avg_temp_c - 18.3 (perfect collinearity), and
#    is_weekend is dropped because the day_of_week dummies already encode it.
OLS_NUM = ["cooling_degree", "heating_degree", "temp_sq", "temp_delta_24", "is_holiday"] + LAGS
def design(d, cols=None):
    X = pd.concat([d[OLS_NUM], pd.get_dummies(d[CAL].astype(str), drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X, has_constant="add")
    return X if cols is None else X.reindex(columns=cols, fill_value=0)
train_ols = train.dropna(subset=["temp_delta_24"])
X_train = design(train_ols)
ols = sm.OLS(train_ols.demand_mwh, X_train).fit()
preds["Linear regression (OLS)"] = ols.predict(design(test, X_train.columns))
print(f"OLS R^2 on train: {ols.rsquared:.3f}")

# 3a. Gradient boosting, default settings, predicting load directly
gb_default = HistGradientBoostingRegressor(random_state=0).fit(train[BASE_FEATURES], train.demand_mwh)
preds["Gradient boosting (default)"] = gb_default.predict(test[BASE_FEATURES])

# 3b. Gradient boosting, default settings, predicting the change from the same hour yesterday.
#     Trees cannot extrapolate past the training range; anchoring on yesterday's load lets the
#     model handle 2024-25 load levels it never saw in training.
gb = HistGradientBoostingRegressor(random_state=0).fit(
    train_ols[FINAL_FEATURES], train_ols.demand_mwh - train_ols.demand_lag_24)
preds["Gradient boosting (change vs yesterday)"] = test.demand_lag_24 + gb.predict(test[FINAL_FEATURES])

# 4. The grid operator's own day-ahead forecast (ERCOT, as filed with EIA on Form EIA-930)
preds["ERCOT official day-ahead forecast"] = test.ercot_forecast_mwh

results = pd.DataFrame({k: metrics(test.demand_mwh, v) for k, v in preds.items()}).T.round(2)
results["RMSE (MWh)"] = results["RMSE (MWh)"].round(0).astype(int)
results'''),
    ("code", '''ours = [k for k in results.index if not k.startswith(("Baseline", "Reference", "ERCOT"))]
best_name = results.loc[ours, "MAPE (%)"].idxmin()
print("best model of ours:", best_name)
test["pred_best"] = preds[best_name]
test["pred_baseline"] = preds["Baseline: same hour last week"]
test["ape_best"] = 100 * (test.demand_mwh - test.pred_best).abs() / test.demand_mwh
test["ape_baseline"] = 100 * (test.demand_mwh - test.pred_baseline).abs() / test.demand_mwh
test["ape_ercot"] = 100 * (test.demand_mwh - test.ercot_forecast_mwh).abs() / test.demand_mwh
results.to_csv("data/clean/model_results.csv")
test[["period", "local_ts", "local_hour", "season", "is_holiday", "demand_mwh", "avg_temp_c",
      "pred_best", "pred_baseline", "ercot_forecast_mwh", "ape_best", "ape_baseline", "ape_ercot"]].to_parquet("data/clean/test_predictions.parquet", index=False)'''),
    ("md", "## Our model vs ERCOT, head to head"),
    ("code", '''daily = test.groupby(test.local_ts.dt.date).agg(ours=("ape_best", "mean"), ercot=("ape_ercot", "mean"),
                                                min_temp=("avg_temp_c", "min"), max_temp=("avg_temp_c", "max"))
print(f"days where our model beats ERCOT: {100 * (daily.ours < daily.ercot).mean():.1f}% of {len(daily)}")
print(f"hours where our model beats ERCOT: {100 * (test.ape_best < test.ape_ercot).mean():.1f}%")
print(f"bias (forecast - actual): ERCOT {(test.ercot_forecast_mwh - test.demand_mwh).mean():+.0f} MWh, ours {(test.pred_best - test.demand_mwh).mean():+.0f} MWh")
display(test.groupby(test.period.dt.year)[["ape_best", "ape_ercot"]].mean().round(2))
gap = daily.assign(gap=daily.ours - daily.ercot)
print("Days ERCOT beat us by the most:")
display(gap.sort_values("gap", ascending=False).head(5).round(1))
print("Days we beat ERCOT by the most:")
gap.sort_values("gap").head(5).round(1)'''),
    ("md", """## ERCOT API: the 9:30 am day-ahead posting, every forecast model
ERCOT re-posts its 7-day forecast every hour. `src/pull_ercot.py` keeps, for each delivery day, the posting made at 09:30 Central the day before (the last one before the 10:00 day-ahead market closes), for all of ERCOT's forecast models, with the model ERCOT flagged as in use."""),
    ("code", '''display(q("SELECT * FROM ercot_model_accuracy"))
display(q("SELECT * FROM ercot_model_in_use"))
api = q("SELECT period, system_total_mwh AS ercot_api_mwh FROM fact_ercot_forecast_model WHERE in_use")
api = api.groupby("period", as_index=False).ercot_api_mwh.mean()   # guard against two in-use rows
cmp = test.merge(api, on="period", how="inner")
print(f"hours with an ERCOT API forecast: {len(cmp):,} of {len(test):,}")
head = pd.DataFrame({
    "ERCOT 9:30 am posting, in-use model (ERCOT API)": metrics(cmp.demand_mwh, cmp.ercot_api_mwh),
    "ERCOT day-ahead forecast (EIA-930 copy)": metrics(cmp.demand_mwh, cmp.ercot_forecast_mwh),
    f"Ours: {best_name}": metrics(cmp.demand_mwh, cmp.pred_best),
    "Baseline: same hour last week": metrics(cmp.demand_mwh, cmp.pred_baseline),
}).T.round(2)
head.to_csv("data/clean/ercot_api_comparison.csv")
head'''),
    ("md", """## Does our model add anything to ERCOT's? A blend, weight chosen on 2024, tested on 2025
If a weighted average of our forecast and ERCOT's beats ERCOT alone, our model carries information ERCOT's forecast misses. The weight is fit on 2024 only, then scored on 2025."""),
    ("code", '''def mape(y, p):
    return float(100 * ((y - p).abs() / y).mean())
c24, c25 = cmp[cmp.period.dt.year == 2024], cmp[cmp.period.dt.year == 2025]
grid = np.round(np.arange(0, 1.01, 0.05), 2)
fit = pd.Series({w: mape(c24.demand_mwh, w * c24.pred_best + (1 - w) * c24.ercot_api_mwh) for w in grid})
w = fit.idxmin()
blend25 = w * c25.pred_best + (1 - w) * c25.ercot_api_mwh
blend = pd.DataFrame({
    "ERCOT alone (API, in-use)": {"MAPE 2025 (%)": mape(c25.demand_mwh, c25.ercot_api_mwh)},
    "Ours alone": {"MAPE 2025 (%)": mape(c25.demand_mwh, c25.pred_best)},
    f"Blend: {w:.2f} ours + {1 - w:.2f} ERCOT": {"MAPE 2025 (%)": mape(c25.demand_mwh, blend25)},
}).T.round(2)
blend["weight on ours (fit on 2024)"] = [np.nan, np.nan, w]
blend.to_csv("data/clean/blend_2025.csv")
blend'''),
    ("code", 'q("SELECT * FROM ercot_zone_accuracy")'),
    ("md", "## Where does it fail?"),
    ("code", '''by_hour = test.groupby("local_hour")[["ape_best", "ape_baseline", "ape_ercot"]].mean().round(2)
by_season = test.groupby("season")[["ape_best", "ape_baseline", "ape_ercot"]].mean().round(2).loc[["Winter", "Spring", "Summer", "Fall"]]
display(by_season); by_hour.T'''),
    ("code", '''print("holiday vs non-holiday MAPE (best model):")
display(test.groupby("is_holiday").ape_best.mean().round(2))
worst_days = (test.groupby(test.local_ts.dt.date)
                  .agg(mape=("ape_best", "mean"), peak_mwh=("demand_mwh", "max"),
                       min_temp=("avg_temp_c", "min"), max_temp=("avg_temp_c", "max"), holiday=("is_holiday", "max"))
                  .sort_values("mape", ascending=False).head(10).round(1))
worst_days'''),
])

# ---------------------------------------------------------------- 03 charts
build("03_charts.ipynb", [
    ("md", "# 03 · Charts\nEach chart is saved as `charts/<name>.png` (static) and `charts/<name>.html` (interactive)."),
    ("code", SETUP + '''
import plotly.graph_objects as go
from viz import add_caption, save, SERIES, FUEL_COLORS, INK, INK_2'''),
    ("md", "## 1. Load vs temperature"),
    ("code", '''m = q("SELECT avg_temp_c, demand_mwh FROM model_hourly WHERE demand_mwh IS NOT NULL")
binned = m.assign(t=m.avg_temp_c.round()).groupby("t").demand_mwh.mean().reset_index()
low = binned.loc[binned.demand_mwh.idxmin()]
fig = go.Figure()
fig.add_scattergl(x=m.avg_temp_c, y=m.demand_mwh / 1000, mode="markers", name="Hourly load",
                  marker=dict(size=3, color=SERIES[0], opacity=0.12),
                  hovertemplate="%{x:.1f} °C<br>%{y:.1f} GW<extra></extra>")
fig.add_scatter(x=binned.t, y=binned.demand_mwh / 1000, mode="lines", name="Average per 1 °C",
                line=dict(color=SERIES[1], width=3), hovertemplate="%{x:.0f} °C<br>avg %{y:.1f} GW<extra></extra>")
fig.add_annotation(x=low.t, y=low.demand_mwh / 1000, text=f"Lowest average load near {low.t:.0f} °C",
                   showarrow=True, arrowcolor=INK_2, ay=60, font=dict(color=INK))
fig.add_annotation(x=-11, y=47, text="Below −9 °C: Uri hours,<br>load shed, not true demand", showarrow=False,
                   xanchor="center", yanchor="top", yshift=-14, font=dict(color=INK_2, size=12))
fig.update_layout(title="ERCOT hourly load vs temperature, 2019–2025",
                  xaxis_title="Load-weighted temperature, 8 Texas cities (°C)", yaxis_title="Hourly load (GW)")
add_caption(fig, "Load is U-shaped in temperature: it bottoms out in mild weather and climbs fastest in summer heat.")
save(fig, "load_vs_temperature")'''),
    ("md", "## 2. Net load and the duck curve\nAverage spring-day (March–May) net load profile, comparing three years."),
    ("code", '''n = q("""SELECT year, local_hour, AVG(net_load_mwh) / 1000 AS net_gw
         FROM net_load_hourly WHERE month(local_ts) IN (3, 4, 5) AND year IN (2019, 2022, 2025)
         GROUP BY year, local_hour ORDER BY year, local_hour""")
fig = go.Figure()
for i, (yr, g) in enumerate(n.groupby("year")):
    fig.add_scatter(x=g.local_hour, y=g.net_gw, mode="lines", name=str(yr), line=dict(color=SERIES[i], width=2.5),
                    hovertemplate=f"{yr} · %{{x}}:00<br>%{{y:.1f}} GW<extra></extra>")
    fig.add_annotation(x=23, y=g.net_gw.iloc[-1], text=str(yr), showarrow=False, xanchor="left", xshift=6,
                       yshift={2019: 9, 2022: -9}.get(yr, 0), font=dict(color=INK))
r25 = n[n.year == 2025].set_index("local_hour").net_gw
fig.add_annotation(x=r25.idxmin(), y=r25.min(), text=f"2025 midday trough {r25.min():.0f} GW", showarrow=True, ay=40, arrowcolor=INK_2, font=dict(color=INK))
fig.update_layout(title="The duck curve: average spring-day net load (demand minus wind and solar)",
                  xaxis_title="Hour ending (Central time)", yaxis_title="Net load (GW)", xaxis=dict(dtick=3, range=[0, 24.5]))
ramp = q("SELECT * FROM evening_ramp_yearly")
add_caption(fig, f"Midday net load has sunk as solar grew; the average evening 3-hour ramp rose from {ramp.avg_daily_max_ramp_mwh.iloc[0]/1000:.1f} GW (2019) to {ramp.avg_daily_max_ramp_mwh.iloc[-1]/1000:.1f} GW (2025).")
save(fig, "duck_curve")'''),
    ("md", "## 3. Winter Storm Uri"),
    ("code", '''u = q("""SELECT local_ts, demand_mwh, gas_mwh, coal_mwh, nuclear_mwh, wind_mwh, solar_mwh,
                COALESCE(hydro_mwh,0) + COALESCE(other_mwh,0) AS other_mwh, avg_temp_c, ercot_forecast_mwh
         FROM model_hourly WHERE local_date BETWEEN DATE '2021-02-11' AND DATE '2021-02-21' ORDER BY period""")
fig = go.Figure()
stack = [("Nuclear", "nuclear_mwh"), ("Coal", "coal_mwh"), ("Gas", "gas_mwh"), ("Wind", "wind_mwh"), ("Solar", "solar_mwh"), ("Other", "other_mwh")]
for name, col in stack:
    fig.add_scatter(x=u.local_ts, y=u[col] / 1000, name=name, stackgroup="gen", mode="lines",
                    line=dict(width=0.5, color="#fcfcfb"), fillcolor=FUEL_COLORS[name],
                    hovertemplate=f"{name}: %{{y:.1f}} GW<extra></extra>")
fig.add_scatter(x=u.local_ts, y=u.ercot_forecast_mwh / 1000, name="ERCOT day-ahead forecast", mode="lines",
                line=dict(color=INK, width=2, dash="dot"), hovertemplate="ERCOT forecast: %{y:.1f} GW<extra></extra>")
fig.add_scatter(x=u.local_ts, y=u.demand_mwh / 1000, name="Served demand", mode="lines",
                line=dict(color=INK, width=2.5), hovertemplate="Demand: %{y:.1f} GW<extra></extra>")
pk = u.loc[u.demand_mwh.idxmax()]
fig.add_annotation(x=pk.local_ts, y=pk.demand_mwh / 1000, text=f"Peak {pk.demand_mwh/1000:.1f} GW", showarrow=True, ay=-30, ax=-70, arrowcolor=INK_2, font=dict(color=INK))
fig.add_vrect(x0="2021-02-15 01:00", x1="2021-02-18 23:00", fillcolor="#8a8984", opacity=0.08, line_width=0,
              annotation_text="Rolling outages: served demand capped by supply", annotation_position="top left",
              annotation_font=dict(color=INK_2))
mid = u[u.local_ts == "2021-02-12 12:00"].iloc[0]
for name, col in [("Nuclear", "nuclear_mwh"), ("Coal", "coal_mwh"), ("Gas", "gas_mwh"), ("Wind", "wind_mwh")]:
    y = (mid[[c for _, c in stack][:[c for _, c in stack].index(col) + 1]].sum() - mid[col] / 2) / 1000
    fig.add_annotation(x=mid.local_ts, y=y, text=name, showarrow=False, font=dict(color="white", size=13))
fig.update_layout(title="Winter Storm Uri, Feb 11–21 2021: ERCOT generation by fuel vs demand",
                  xaxis_title="Date (Central time)", yaxis_title="Hourly energy (GW)", yaxis=dict(range=[0, 85]))
out = u[(u.local_ts >= "2021-02-15") & (u.local_ts < "2021-02-19")]
gap = (out.ercot_forecast_mwh - out.demand_mwh).clip(lower=0)
add_caption(fig, f"Generation fell nearly 40% after the Feb 14 peak. ERCOT's own forecast ran up to {gap.max()/1000:.0f} GW above served demand, an upper bound on load shed.")
save(fig, "uri_week")'''),
])
# ---------------------------------------------------------------- 04 gas prices
GAS_INTRO = """# 04 · Gas prices and the generation mix
**Question:** when natural gas gets expensive, how much does ERCOT shift from gas to coal?

Gas and coal compete for the load left after wind, solar and nuclear, so the outcome is
**gas share of fossil generation** = gas / (gas + coal), by day. Price is the daily Henry Hub spot
(weekends and holidays carry the last trading day's price via an ASOF join).
Uri (Feb 10–20 2021) is excluded: prices spiked to $23.86 while plants were failing, which is not economic dispatch."""

GAS_REG_MD = """## Controlled regression
Raw comparisons are confounded: gas prices run high in cold snaps and heat waves, exactly when coal is already running flat out.
So regress gas share of fossil on log price, controlling for net load (and its square), month and year.
Standard errors are Newey-West (HAC, 7 lags) because neighbouring days are correlated."""

build("04_gas_prices.ipynb", [
    ("md", GAS_INTRO),
    ("code", SETUP),
    ("code", 'q("SELECT * FROM gas_price_quintiles")'),
    ("code", 'q("SELECT * FROM gas_price_by_year")'),
    ("md", GAS_REG_MD),
    ("code", '''import statsmodels.formula.api as smf
d = q("SELECT * FROM gas_daily WHERE NOT is_uri ORDER BY local_date")   # Newey-West needs rows in time order
d["log_p"] = np.log(d.henry_hub_usd)
d["nl_gw"] = d.net_load_mwh / 24 / 1000
LN2 = np.log(2)
pooled = smf.ols("gas_fossil_share_pct ~ log_p + nl_gw + I(nl_gw**2) + C(month) + C(year)", d).fit(
    cov_type="HAC", cov_kwds={"maxlags": 7})
b, se = pooled.params["log_p"] * LN2, pooled.bse["log_p"] * LN2
print(f"Doubling Henry Hub shifts gas share of fossil generation by {b:+.2f} pts "
      f"(95% CI {b - 1.96 * se:+.2f} to {b + 1.96 * se:+.2f}); R^2 {pooled.rsquared:.2f}")
print(f"Average gas share of fossil generation: {d.gas_fossil_share_pct.mean():.1f}%")'''),
    ("code", '''rows = []
for yr, g in d.groupby("year"):
    m = smf.ols("gas_fossil_share_pct ~ log_p + nl_gw + I(nl_gw**2) + C(month)", g).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7})
    rows.append({"year": yr, "shift_per_doubling_pts": m.params["log_p"] * LN2, "ci95": 1.96 * m.bse["log_p"] * LN2,
                 "price_min": g.henry_hub_usd.min(), "price_max": g.henry_hub_usd.max(),
                 "gas_fossil_share_pct": g.gas_fossil_share_pct.mean(), "coal_share_pct": g.coal_share_pct.mean(),
                 "days": len(g)})
by_year = pd.DataFrame(rows).round(2)
by_year.to_csv("data/clean/gas_switching_by_year.csv", index=False)
by_year'''),
    ("code", '''import plotly.graph_objects as go
from viz import add_caption, save, SERIES, INK_2
fig = go.Figure(go.Bar(x=by_year.year, y=by_year.shift_per_doubling_pts, marker_color=SERIES[0], name="Shift per doubling",
                       error_y=dict(type="data", array=by_year.ci95, color=INK_2, thickness=1.5, width=6),
                       hovertemplate="%{x}: %{y:+.1f} pts<extra></extra>"))
fig.add_hline(y=0, line=dict(color=INK_2, width=1))
fig.update_layout(title="How much gas loses to coal when gas prices double, by year", bargap=0.45,
                  xaxis_title="Year", yaxis_title="Change in gas share of fossil generation (pts)", xaxis=dict(dtick=1))
first, late = by_year.iloc[0], by_year[by_year.year >= 2022]
add_caption(fig, f"Fuel switching looks weaker: {first.shift_per_doubling_pts:+.1f} pts per doubling in {int(first.year)}, {late.shift_per_doubling_pts.min():+.1f} to {late.shift_per_doubling_pts.max():+.1f} since 2022. Pooled: {b:+.1f} pts. Bars: 95% CI. Descriptive, not causal.")
save(fig, "gas_price_switching")'''),
    ("md", """## Why did switching fade? Testing the coal-capacity story
Two threats to reading the regression above as "gas price causes switching, and coal retirements ended it":
1. **Weather moves everything.** Cold snaps and heat waves raise gas prices and demand and take plants offline, so the price coefficient can pick up weather. Below I add heating and cooling degrees, and rerun on mild days only.
2. **Behavior vs. capacity.** The year-by-year fade lines up with coal retirements, but the year-by-year regression can't say which caused it.

There is no coal fleet capacity in this data, so I build two proxies from coal output itself, using only earlier days so today's dispatch can't feed into them:
- **Capacity proxy:** the highest hourly coal output in the previous 30 days.
- **Headroom:** that proxy minus average coal output over the previous 30 days, i.e. how much spare coal was recently available.

If lost capacity explains the fade, the price-by-capacity interaction should be significant and adding it should shrink the price-by-time trend. Henry Hub is still a national price: no free daily Texas hub series (Houston Ship Channel, Waha) was available, so this remains descriptive rather than causal."""),
    ("code", '''h = q("""SELECT local_date, MAX(coal_mwh) AS coal_max, AVG(coal_mwh) AS coal_avg,
                  AVG(GREATEST(avg_temp_c - 18.3, 0)) AS cdd, AVG(GREATEST(18.3 - avg_temp_c, 0)) AS hdd,
                  MIN(avg_temp_c) AS tmin, MAX(avg_temp_c) AS tmax
           FROM model_hourly GROUP BY 1 ORDER BY 1""")
h["coal_cap_gw"] = h.coal_max.shift(1).rolling(30, min_periods=10).max() / 1000
h["headroom_gw"] = h.coal_cap_gw - h.coal_avg.shift(1).rolling(30, min_periods=10).mean() / 1000
g = d.merge(h, on="local_date").dropna(subset=["coal_cap_gw"]).copy()
g["cap_c"] = g.coal_cap_gw - g.coal_cap_gw.mean()
g["head_c"] = g.headroom_gw - g.headroom_gw.mean()
g["t_c"] = (pd.to_datetime(g.local_date) - pd.Timestamp("2022-07-01")).dt.days / 365.25
CTL = "nl_gw + I(nl_gw**2) + cdd + I(cdd**2) + hdd + I(hdd**2) + C(month) + C(year)"
HAC = dict(cov_type="HAC", cov_kwds={"maxlags": 7})
SPECS = {
    "Add weather controls": ("log_p + " + CTL, g),
    "Weather, mild days only": ("log_p + " + CTL, g[(g.tmin > 0) & (g.tmax < 33)]),
    "Add coal capacity proxy": ("log_p + cap_c + " + CTL, g),
    "Price x capacity": ("log_p * cap_c + " + CTL, g),
    "Price x time": ("log_p + log_p:t_c + " + CTL, g),
    "Price x headroom": ("log_p * head_c + " + CTL, g),
    "Price x headroom, price x time": ("log_p * head_c + log_p:t_c + " + CTL, g),
}
rows = []
for name, (rhs, data) in SPECS.items():
    m = smf.ols("gas_fossil_share_pct ~ " + rhs, data).fit(**HAC)
    row = {"spec": name, "days": int(m.nobs)}
    for term, label in [("log_p", "per doubling"), ("log_p:cap_c", "x capacity (per GW)"),
                        ("log_p:head_c", "x headroom (per GW)"), ("log_p:t_c", "x time (per year)")]:
        if term in m.params:
            row[label] = round(m.params[term] * LN2, 2)
            row[label + " p"] = round(m.pvalues[term], 3)
    rows.append(row)
robust = pd.DataFrame(rows)
robust.to_csv("data/clean/gas_robustness.csv", index=False)
display(robust)
g.groupby("year")[["coal_cap_gw", "headroom_gw"]].mean().round(2)'''),
])
# ---------------------------------------------------------------- 05 growth, drivers, misses
build("05_drivers_and_misses.ipynb", [
    ("md", """# 05 · Weather-adjusted growth, and diagnostics on the hindsight model\nSections 2 to 4 study the hindsight model from notebook 02. Notebook 06 repeats the importance and misses analysis for the 9:30 am model."""),
    ("code", SETUP + '''
import statsmodels.formula.api as smf
import plotly.graph_objects as go
from viz import add_caption, save, SERIES, INK, INK_2'''),
    ("md", """## 1. Weather-adjusted demand growth
Peak load rose about 15% from 2019 to the 2024 record. Is that growth, or hotter summers?
Fit **log(load)** on temperature (cooling and heating degrees and their squares, each allowed to differ by hour of day),
hour, weekday, month and holidays, plus a **year effect**. The year effect is the change in load at identical weather and calendar.
Uri (Feb 10–20 2021) and the Hurricane Beryl outage period (Jul 8–17 2024) are excluded because load there was lost to outages, not weather.
A second fit uses only summer afternoons (Jun–Sep, hour ending 2–8 pm), the hours that set the annual peak."""),
    ("code", '''df = q("SELECT * FROM model_hourly WHERE year BETWEEN 2019 AND 2025 ORDER BY period")
w = df[~df.local_date.between("2021-02-10", "2021-02-20")
       & ~df.local_date.between("2024-07-08", "2024-07-17")
       & ~df.is_imputed.astype(bool)].copy()
w["cdd"] = (w.avg_temp_c - 18.3).clip(lower=0)
w["hdd"] = (18.3 - w.avg_temp_c).clip(lower=0)
w["log_d"] = np.log(w.demand_mwh)
YEARS = range(2020, 2026)

all_hours = smf.ols("log_d ~ C(year) + (cdd + I(cdd**2) + hdd + I(hdd**2)):C(local_hour)"
                    " + C(local_hour) + C(day_of_week) + is_holiday + C(month)", w).fit()
summer = w[w.month.between(6, 9) & w.local_hour.between(14, 20)]
summer_fit = smf.ols("log_d ~ C(year) + (cdd + I(cdd**2)):C(local_hour) + C(local_hour)"
                     " + C(day_of_week) + is_holiday + C(month)", summer).fit()
print(f"R^2 all hours {all_hours.rsquared:.3f}, summer afternoons {summer_fit.rsquared:.3f}")

def year_pct(m):
    return {2019: 0.0, **{y: 100 * (np.exp(m.params[f"C(year)[T.{y}]"]) - 1) for y in YEARS}}
def year_ci(m):
    return {2019: 0.0, **{y: 100 * 1.96 * m.bse[f"C(year)[T.{y}]"] for y in YEARS}}

raw_avg = w.groupby("year").demand_mwh.mean()
peak = q("SELECT year, peak_mwh FROM peak_growth_yearly").set_index("year").peak_mwh
growth = pd.DataFrame({
    "raw average load vs 2019 (%)": 100 * (raw_avg / raw_avg[2019] - 1),
    "weather-adjusted, all hours (%)": year_pct(all_hours),
    "weather-adjusted, summer afternoons (%)": year_pct(summer_fit),
    "raw annual peak vs 2019 (%)": 100 * (peak / peak[2019] - 1),
    "summer cooling degrees (avg °C above 18.3)": w[w.month.between(6, 9)].groupby("year").cdd.mean(),
}).round(2)
growth.to_csv("data/clean/weather_adjusted_growth.csv")
growth'''),
    ("code", '''# Where the growth is: average load by ERCOT weather zone, full clean years only
# (zone data starts May 2019 and drifts from the ERCOT total in 2024-25, see qa_zone_mismatch)
q("""SELECT zone,
            ROUND(AVG(demand_mwh) FILTER (WHERE year(period) = 2020)) AS avg_2020_mwh,
            ROUND(AVG(demand_mwh) FILTER (WHERE year(period) = 2023)) AS avg_2023_mwh,
            ROUND(100 * (AVG(demand_mwh) FILTER (WHERE year(period) = 2023)
                       / AVG(demand_mwh) FILTER (WHERE year(period) = 2020) - 1), 1) AS growth_pct
     FROM fact_zone_load GROUP BY zone ORDER BY growth_pct DESC""")'''),
    ("code", '''fig = go.Figure()
series = [("raw average load vs 2019 (%)", "Actual average load", "Actual"),
          ("weather-adjusted, all hours (%)", "Weather-adjusted, all hours", "Weather-adjusted"),
          ("weather-adjusted, summer afternoons (%)", "Weather-adjusted, summer afternoons", "Summer afternoons")]
for i, (col, name, short) in enumerate(series):
    fig.add_scatter(x=growth.index, y=growth[col], mode="lines+markers", name=name,
                    line=dict(color=SERIES[i], width=2.5), marker=dict(size=8),
                    hovertemplate=f"{short} · %{{x}}: %{{y:+.1f}}%<extra></extra>")
    fig.add_annotation(x=2025, y=growth[col].iloc[-1], text=f"{short} {growth[col].iloc[-1]:+.0f}%", showarrow=False,
                       xanchor="left", xshift=8, font=dict(color=INK))
fig.add_hline(y=0, line=dict(color=INK_2, width=1))
fig.update_layout(title="ERCOT load growth since 2019, with and without weather",
                  xaxis_title="Year", yaxis_title="Change vs 2019 (%)", xaxis=dict(tickvals=list(range(2019, 2026)), range=[2018.7, 2026.3]),
                  margin=dict(r=190))
adj = growth["weather-adjusted, all hours (%)"]
add_caption(fig, f"At identical weather, ERCOT load grew {adj[2025]:.0f}% from 2019 to 2025, about {100*((1+adj[2025]/100)**(1/6)-1):.1f}% a year. Hotter summers are not the explanation.")
save(fig, "weather_adjusted_growth")'''),
    ("md", """## 2. What drives the model: each city separately
Same day-ahead setup as notebook 02 (train 2019–2023, predict the change from yesterday, test 2024–2025), but with each of the 8 cities' temperature (and its value 24 h earlier) as separate inputs instead of the weighted average.
**Grouped permutation importance:** shuffle one group of inputs on the test set (for a city, both its temperature columns together), and measure how much MAPE rises. Five shuffles per group.
Caveat: city temperatures are correlated, so cities that move together split the credit. A low score means "adds little the other cities don't already carry", not "irrelevant\""""),
    ("code", '''from sklearn.ensemble import HistGradientBoostingRegressor
cities = q("PIVOT (SELECT period, city, temp_c FROM fact_weather) ON city USING first(temp_c)")
name_of = {f"t_{c.lower().replace(' ', '_')}": c for c in cities.columns[1:]}
cities.columns = ["period"] + list(name_of)
d = df.merge(cities, on="period").sort_values("period")
tcols = list(name_of)
for c in tcols:
    d[c + "_lag24"] = d[c].shift(24)
d["is_weekend"] = d.is_weekend.astype(int)
d["is_holiday"] = d.is_holiday.astype(int)
d = d.dropna(subset=["demand_lag_168"] + [c + "_lag24" for c in tcols])
base = ["local_hour", "day_of_week", "month", "is_weekend", "is_holiday"]   # no load-level inputs, as in notebook 02
feats = base + tcols + [c + "_lag24" for c in tcols]
tr, te = d[d.period.dt.year <= 2023], d[d.period.dt.year >= 2024]
gb = HistGradientBoostingRegressor(random_state=0).fit(tr[feats], tr.demand_mwh - tr.demand_lag_24)
def mape_of(X):
    p = te.demand_lag_24.values + gb.predict(X[feats])   # anchor stays the true value; only model inputs are shuffled
    return 100 * np.mean(np.abs(te.demand_mwh.values - p) / te.demand_mwh.values)
base_mape = mape_of(te)
print(f"per-city model, test MAPE: {base_mape:.2f}%  (compare the weighted-average model in notebook 02)")

groups = {name_of[c]: [c, c + "_lag24"] for c in tcols}
groups.update({"Hour of day": ["local_hour"], "Day of week": ["day_of_week"], "Month": ["month"],
               "Holiday / weekend": ["is_holiday", "is_weekend"]})
rng = np.random.default_rng(0)
rows = []
for g, cols in groups.items():
    rises = []
    for _ in range(5):
        X = te.copy()
        idx = rng.permutation(len(X))
        for c in cols:
            X[c] = X[c].values[idx]
        rises.append(mape_of(X) - base_mape)
    rows.append({"input": g, "is_city": g in name_of.values(), "mape_increase_pts": np.mean(rises), "sd": np.std(rises)})
imp = pd.DataFrame(rows).sort_values("mape_increase_pts", ascending=False).round(3)
imp.to_csv("data/clean/feature_importance.csv", index=False)
imp'''),
    ("md", """## 3. The model's 10 biggest misses
Worst days on the test set by daily MAPE for the main model (notebook 02). The context column is generated from the data: holidays, the day after a holiday (the model anchors on yesterday's load), freezing or extreme heat, and big temperature swings from the day before. The one hand-labelled event is Hurricane Beryl."""),
    ("code", '''t = pd.read_parquet("data/clean/test_predictions.parquet")
t["local_date"] = t.local_ts.dt.normalize()
t["err"] = t.pred_best - t.demand_mwh
hol = pd.read_parquet("data/clean/us_holidays.parquet")
hol = dict(zip(pd.to_datetime(hol.holiday_date), hol.holiday_name))
tl = q("SELECT period, avg_temp_c - temp_lag_24 AS temp_delta_24 FROM model_hourly")
t = t.merge(tl, on="period", how="left")
KNOWN = {pd.Timestamp("2024-07-08"): "Hurricane Beryl made landfall near Houston; about 2.2 million customers lost power"}

def worst_hour(g):
    r = g.loc[g.err.abs().idxmax()]
    return pd.Series({"worst_hour_ending": int(r.local_hour), "worst_hour_error_gw": r.err / 1000})

days = t.groupby("local_date").agg(our_mape=("ape_best", "mean"), ercot_mape=("ape_ercot", "mean"),
                                   mean_error_gw=("err", lambda e: e.mean() / 1000), min_temp=("avg_temp_c", "min"),
                                   max_temp=("avg_temp_c", "max"), max_swing=("temp_delta_24", lambda s: s.abs().max()))
days = days.join(t.groupby("local_date")[["err", "local_hour"]].apply(worst_hour))
worst = days.sort_values("our_mape", ascending=False).head(10).copy()

def context(day, r):
    notes = []
    if day in KNOWN: notes.append(KNOWN[day])
    if day in hol: notes.append(f"Holiday: {hol[day]}")
    y = day - pd.Timedelta(days=1)
    if y in hol: notes.append(f"Day after {hol[y]}: the model anchors on yesterday's holiday-level load")
    if day - pd.Timedelta(days=2) in hol and y not in hol:
        notes.append(f"Two days after {hol[day - pd.Timedelta(days=2)]}")
    if r.min_temp <= 0: notes.append(f"Freezing: low of {r.min_temp:.0f} °C")
    if r.max_temp >= 37: notes.append(f"Extreme heat: high of {r.max_temp:.0f} °C")
    if r.max_swing >= 8: notes.append(f"Temperature swung up to {r.max_swing:.0f} °C from the day before")
    return "; ".join(notes) or "No clear driver in our data"

worst["weekday"] = worst.index.day_name()
worst["direction"] = np.where(worst.mean_error_gw > 0, "over-forecast", "under-forecast")
worst["context"] = [context(day, r) for day, r in worst.iterrows()]
worst = worst.reset_index()[["local_date", "weekday", "our_mape", "ercot_mape", "direction", "worst_hour_ending",
                             "worst_hour_error_gw", "min_temp", "max_temp", "max_swing", "context"]].round(1)
worst["local_date"] = worst.local_date.dt.date
worst.to_csv("data/clean/biggest_misses.csv", index=False)
worst'''),
    ("md", """## 4. The 6 pm question: do people get home and turn on the heat (or AC)?
Hour ending 6 pm was the model's worst hour. The theory: on workdays, people get home around 6 pm and switch on heating in winter or AC in summer, so a correction for cold or hot *workday* evenings should help.

The test has to avoid leaking the test set:
1. **Errors to learn from:** train the model on 2019–2022 and take its errors on 2023 (validation).
2. **Fit the correction:** regress those 6 pm errors on heating degrees, cooling degrees, a workday flag and their interactions.
3. **Check it:** apply the correction to the 2024–25 test forecasts and see whether 6 pm error falls.

This analysis also found why 6 pm looked so bad. The original model used yesterday's and last week's load *levels* as inputs. It learned the 2019–23 pattern that high-load days are followed by drops. In 2024–25, load is high every day because of growth, so it under-forecast every hour by about 1,000 MWh, most of all at the evening peak."""),
    ("code", '''import warnings
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor
m6 = df.copy()
m6["cooling_degree"] = (m6.avg_temp_c - 18.3).clip(lower=0)
m6["heating_degree"] = (18.3 - m6.avg_temp_c).clip(lower=0)
m6["temp_sq"] = m6.avg_temp_c ** 2
m6["temp_delta_24"] = m6.avg_temp_c - m6.temp_lag_24
m6["is_weekend"] = m6.is_weekend.astype(int)
m6["is_holiday"] = m6.is_holiday.astype(int)
m6["workday"] = ((m6.is_weekend == 0) & (m6.is_holiday == 0)).astype(int)
m6 = m6.dropna(subset=["demand_lag_168", "temp_delta_24"])
NO_LEVELS = ["avg_temp_c", "cooling_degree", "heating_degree", "temp_sq", "is_weekend", "is_holiday",
             "local_hour", "day_of_week", "month", "temp_delta_24"]
WITH_LEVELS = NO_LEVELS + ["demand_lag_24", "demand_lag_168"]
yr = m6.period.dt.year

def residuals(feats, train_to, target_years):
    tr, tg = m6[yr <= train_to], m6[yr.isin(target_years)].copy()
    gbm = HistGradientBoostingRegressor(random_state=0).fit(tr[feats], tr.demand_mwh - tr.demand_lag_24)
    tg["pred"] = tg.demand_lag_24 + gbm.predict(tg[feats])
    tg["resid"] = tg.demand_mwh - tg.pred          # positive = under-forecast
    tg["ape"] = 100 * tg.resid.abs() / tg.demand_mwh
    return tg

rows = {}
for label, feats in [("with load-level inputs (original)", WITH_LEVELS), ("without (current)", NO_LEVELS)]:
    v, t_ = residuals(feats, 2022, [2023]), residuals(feats, 2023, [2024, 2025])
    rows[label] = {"val 2023 MAPE": v.ape.mean(), "val bias MWh": v.resid.mean(), "test MAPE": t_.ape.mean(),
                   "test bias MWh": t_.resid.mean(), "test 6 pm MAPE": t_[t_.local_hour == 18].ape.mean()}
pd.DataFrame(rows).T.round(2)'''),
    ("code", '''val6 = residuals(NO_LEVELS, 2022, [2023])
test6 = residuals(NO_LEVELS, 2023, [2024, 2025])
F6 = "resid ~ heating_degree*workday + cooling_degree*workday"
fits = {}
for label, d in [("2023 validation", val6), ("2024-25 test (descriptive only)", test6)]:
    m = smf.ols(F6, d[d.local_hour == 18]).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    fits[label] = pd.DataFrame({"coef_MWh": m.params, "p_value": m.pvalues}).round(3)
display(pd.concat(fits, axis=1))
print("Mean 6 pm error (MWh) by season and day type, 2024-25 test:")
test6[test6.local_hour == 18].groupby(["season", "workday"]).resid.mean().round(0).unstack().rename(columns={0: "weekend/holiday", 1: "workday"})'''),
    ("code", '''# Apply corrections fit on 2023 to the 2024-25 forecasts
out = {}
for hours, hlabel in [([18], "6 pm only"), ([17, 18, 19, 20], "5-8 pm")]:
    for formula, flabel in [(F6, "heating/AC x workday"), ("resid ~ 1", "constant")]:
        corrected = test6.pred.copy()
        for h in hours:
            fit = smf.ols(formula, val6[val6.local_hour == h]).fit()
            msk = test6.local_hour == h
            corrected[msk] += fit.predict(test6[msk])
        ape = 100 * (test6.demand_mwh - corrected).abs() / test6.demand_mwh
        sel = test6.local_hour.isin(hours)
        out[(hlabel, flabel)] = {"MAPE in those hours, before": test6.ape[sel].mean(), "after": ape[sel].mean(),
                                 "overall before": test6.ape.mean(), "overall after": ape.mean()}
six_pm = pd.DataFrame(out).T.round(3)
six_pm.to_csv("data/clean/six_pm_test.csv")
six_pm'''),
])
# ---------------------------------------------------------------- 06 9:30 am forecast
build("06_operational_forecast.ipynb", [
    ("md", '''# 06 · A forecast that only uses what was known at 9:30 am
ERCOT posts its day-ahead forecast at 9:30 am on the day before delivery. The model in notebook 02 used observed temperature and yesterday's load for every hour, so its comparison with ERCOT was not like for like. This notebook removes both advantages.

- **Load:** known only through hour ending 9 on the day before delivery. The rules are asserted in `src/op_forecast.py`.
- **Weather:** archived model forecasts (Open-Meteo Previous Runs), using the newest run already out at 9:30 am. GFS is the main source and JMA fills GFS's archive gap (2023-12-30 to 2024-01-19).
- **Target:** load divided by a baseline, the average of the same hour over recent fully known non-holiday days. Cross-validation below compares 14 and 28 days.
- **Holidays:** left out of the baseline and of the recent-load signals, so a holiday can't drag down the days after it.
- **Recent weather:** rolling 24 and 72 hour forecast temperature and the overnight low, because buildings hold heat and cold.
- **Choices:** inputs are compared with expanding-window cross-validation over 2022 and 2023, and settings are tuned on 2023. The 2024 to 2025 test set is only scored at the end.'''),
    ("code", SETUP + '''
import itertools, warnings
import plotly.graph_objects as go
import op_forecast as op
from viz import add_caption, save, SERIES, INK_2
warnings.filterwarnings("ignore")
base, holidays = op.load_frame(con)
base, city_cols, offset = op.add_forecast_weather(base, con, pd.read_parquet("data/raw/weather_forecast.parquet"),
                                                  pd.read_parquet("data/raw/weather.parquet"))
print(f"forecast minus observed offset used before the archive starts: {offset:+.2f} °C")
X = {n: op.add_load_features(base, holidays, n) for n in [14, 28]}
for x in X.values():
    op.assert_no_leak(x)
e = (base.fc_temp - base.avg_temp_c)[base.period >= "2021-04-01"]
yrs = base.period[base.period >= "2021-04-01"].dt.year
pd.DataFrame({"mean error (°C)": e.groupby(yrs).mean(), "mean absolute error (°C)": e.abs().groupby(yrs).mean()}).round(2)'''),
    ("md", "## Structure and tuning: expanding-window CV, one fold per quarter"),
    ("code", '''def quarters(y):
    return [(f"{y}-01-01", f"{y}-04-01"), (f"{y}-04-01", f"{y}-07-01"), (f"{y}-07-01", f"{y}-10-01"), (f"{y}-10-01", f"{y + 1}-01-01")]
def cv(x, feats, params=None, folds=quarters(2023)):
    d = op.usable(x)
    errs = []
    for a, b in folds:
        tr, va = d[d.op_date < a], d[(d.op_date >= a) & (d.op_date < b)]
        m = op.fit(tr, feats, params)
        errs.append((va.demand_mwh - op.predict(m, va, feats)).abs() / va.demand_mwh)
    return round(100 * pd.concat(errs).mean(), 3)

SETS = {"core": op.CORE, "core + holiday-adjacent flags": op.CORE + op.ADJACENT,
        "core + flags + city temperatures": op.CORE + op.ADJACENT + city_cols,
        "core + flags + cities + recent weather": op.CORE + op.ADJACENT + city_cols + op.THERMAL}
structure = pd.DataFrame([{"baseline days": n, "inputs": k, "CV 2022": cv(X[n], f, folds=quarters(2022)), "CV 2023": cv(X[n], f)}
                          for n, (k, f) in itertools.product(X, SETS.items())])
structure["CV MAPE"] = structure[["CV 2022", "CV 2023"]].mean(axis=1).round(3)
structure.to_csv("data/clean/op_structure_cv.csv", index=False)
structure'''),
    ("code", '''best = structure.loc[structure["CV MAPE"].idxmin()]
x, feats = X[int(best["baseline days"])], SETS[best["inputs"]]
print("chosen:", int(best["baseline days"]), "days,", best["inputs"])
grid = [dict(learning_rate=l, max_iter=i, max_leaf_nodes=n, min_samples_leaf=s)
        for l, i, n, s in itertools.product([0.03, 0.1], [200, 500], [15, 31], [20, 60])]
grid.append(dict(learning_rate=0.1, max_iter=800, max_leaf_nodes=31, min_samples_leaf=20))   # past the edge of the grid
tuning = pd.DataFrame([{**p, "CV MAPE": cv(x, feats, p)} for p in grid]).sort_values("CV MAPE")
tuning.to_csv("data/clean/op_tuning_cv.csv", index=False)
params = tuning.iloc[0].drop("CV MAPE").to_dict()
params = {k: (float(v) if k == "learning_rate" else int(v)) for k, v in params.items()}
print("default settings CV MAPE:", cv(x, feats)); print("chosen:", params)
tuning.head(5)'''),
    ("md", "## Scoring the test set, once"),
    ("code", '''d = op.usable(x)
train, test = d[d.year <= 2023], d[d.year >= 2024].copy()
model = op.fit(train, feats, params)
test["pred"] = op.predict(model, test, feats)
api = q("SELECT period, AVG(system_total_mwh) AS ercot_api_mwh FROM fact_ercot_forecast_model WHERE in_use GROUP BY 1")
api["period"] = pd.to_datetime(api.period, utc=True)
hind = pd.read_parquet("data/clean/test_predictions.parquet")[["period", "pred_best"]].rename(columns={"pred_best": "pred_hindsight"})
hind["period"] = pd.to_datetime(hind.period, utc=True)
lags = q("SELECT period, demand_lag_168 FROM model_hourly"); lags["period"] = pd.to_datetime(lags.period, utc=True)
t = test.merge(api, on="period").merge(hind, on="period").merge(lags, on="period").dropna(subset=["ercot_forecast_mwh"]).copy()
print(f"{len(t):,} test hours scored by every forecast")
y = t.demand_mwh
forecasts = {"Baseline: same hour last week": t.demand_lag_168,
             "Mine, hindsight version (notebook 02)": t.pred_hindsight,
             "Mine, 9:30 am information only": t.pred,
             "ERCOT 9:30 am posting (ERCOT API)": t.ercot_api_mwh,
             "ERCOT day-ahead, EIA-930 copy": t.ercot_forecast_mwh}
results = pd.DataFrame({k: {"RMSE (MWh)": round(op.rmse(y, v)), "MAPE (%)": round(op.mape(y, v), 2), "bias (MWh)": round((v - y).mean())}
                        for k, v in forecasts.items()}).T
results.to_csv("data/clean/op_results.csv")
results'''),
    ("code", '''t["ape"] = 100 * (t.pred - y).abs() / y
t["ape_ercot"] = 100 * (t.ercot_api_mwh - y).abs() / y
days = t.groupby("op_date")[["ape", "ape_ercot"]].mean()
print(f"days mine beats ERCOT's 9:30 am posting: {100 * (days.ape < days.ape_ercot).mean():.1f}% of {len(days)}")
print(f"hours: {100 * (t.ape < t.ape_ercot).mean():.1f}%")
by_year = t.groupby("year")[["ape", "ape_ercot"]].mean().round(2)
by_season = t.groupby("season")[["ape", "ape_ercot"]].mean().round(2).loc[["Winter", "Spring", "Summer", "Fall"]]
display(by_year); display(by_season)
summer_pm = t[t.month.between(6, 9) & t.he.between(16, 20)]
peak = t.groupby("op_date").apply(lambda g: pd.Series({
    "actual": g.demand_mwh.max(), "mine": g.pred.max(), "ercot": g.ercot_api_mwh.max(), "hour_ok_mine": g.pred.idxmax() == g.demand_mwh.idxmax(),
    "hour_ok_ercot": g.ercot_api_mwh.idxmax() == g.demand_mwh.idxmax()}))
peak_rows = {"All hours": (op.mape(y, t.pred), op.mape(y, t.ercot_api_mwh)),
             "Summer, 4 to 8 pm": (op.mape(summer_pm.demand_mwh, summer_pm.pred), op.mape(summer_pm.demand_mwh, summer_pm.ercot_api_mwh)),
             "Size of each day's peak": (op.mape(peak.actual.astype(float), peak.mine.astype(float)), op.mape(peak.actual.astype(float), peak.ercot.astype(float)))}
peaks = pd.DataFrame(peak_rows, index=["mine", "ERCOT"]).T.round(2)
peaks.to_csv("data/clean/op_peak_error.csv")
print(f"peak hour called exactly: mine {100 * peak.hour_ok_mine.astype(float).mean():.0f}%, ERCOT {100 * peak.hour_ok_ercot.astype(float).mean():.0f}%")
peaks'''),
    ("md", "## Did the holiday fix work?\nSame model and settings with holidays left in the baseline and recent-load signals, scored on holidays, the two days after them, and all other days."),
    ("code", '''raw = op.add_load_features(base, holidays, int(best["baseline days"]), skip_holidays=False)
ru = op.usable(raw)
rtr, rte = ru[ru.year <= 2023], ru[ru.year >= 2024].copy()
rte["pred_nofix"] = op.predict(op.fit(rtr, feats, params), rte, feats)
c = t.merge(rte[["period", "pred_nofix"]], on="period")
c["ape_nofix"] = 100 * (c.pred_nofix - c.demand_mwh).abs() / c.demand_mwh
hd = pd.to_datetime(sorted(holidays))
after = set(hd + pd.Timedelta(days=1)) | set(hd + pd.Timedelta(days=2))
c["group"] = np.where(c.holiday == 1, "Holiday", np.where(c.op_date.isin(after), "One or two days after", "Other days"))
hol = c.groupby("group")[["ape_nofix", "ape", "ape_ercot"]].mean().round(2)
hol["hours"] = c.groupby("group").size()
hol.to_csv("data/clean/op_holiday_fix.csv")
hol'''),
    ("md", "## What drives the 9:30 am model\nGrouped permutation importance on the test set: shuffle a group of inputs, measure the rise in MAPE, five shuffles each. The baseline stays fixed. Correlated inputs split credit, so a low score means the input adds little that the others don't carry, not that it is irrelevant."),
    ("code", '''groups = {c.replace("t_", "").replace("_", " ").title(): [c] for c in city_cols}
groups.update({"Statewide temperature": ["fc_temp", "cool", "heat", "temp_sq", "temp_vs_baseline"],
               "Hour of day": ["he"], "Day of week": ["dow", "weekend"], "Month": ["month"],
               "Holiday flags": ["holiday", "day_after_holiday", "day_before_holiday"],
               "Recent weather": op.THERMAL, "Morning load, day before": ["morning_ratio"], "Load two days before": ["d2_ratio"],
               "Baseline temperature": ["baseline_temp"]})
cities = set(c.replace("t_", "").replace("_", " ").title() for c in city_cols)
base_mape = op.mape(t.demand_mwh, op.predict(model, t, feats))
rng = np.random.default_rng(0)
rows = []
for name, cols in groups.items():
    rises = []
    for _ in range(5):
        s = t.copy(); idx = rng.permutation(len(s))
        for c_ in cols:
            s[c_] = s[c_].values[idx]
        rises.append(op.mape(t.demand_mwh, op.predict(model, s, feats)) - base_mape)
    rows.append({"input": name, "is_city": name in cities, "mape_increase_pts": np.mean(rises), "sd": np.std(rises)})
imp = pd.DataFrame(rows).sort_values("mape_increase_pts", ascending=False).round(3)
imp.to_csv("data/clean/op_feature_importance.csv", index=False)
imp'''),
    ("code", '''srt = imp.sort_values("mape_increase_pts")
fig = go.Figure()
for is_city, label, color in [(True, "City temperature", SERIES[0]), (False, "Other input", SERIES[1])]:
    s = srt[srt.is_city == is_city]
    fig.add_bar(y=s.input, x=s.mape_increase_pts, orientation="h", name=label, marker_color=color,
                error_x=dict(type="data", array=s.sd, color=INK_2, thickness=1),
                hovertemplate="%{y}: +%{x:.2f} pts<extra></extra>")
fig.update_layout(title="What drives the 9:30 am forecast (test set 2024–2025)", barmode="overlay", bargap=0.3,
                  xaxis_title="Rise in MAPE when the input is shuffled (percentage points)", yaxis_title="",
                  yaxis=dict(categoryorder="array", categoryarray=list(srt.input), tickmode="array", tickvals=list(srt.input), tickfont=dict(size=12)), margin=dict(l=190, b=170))
add_caption(fig, f"{imp.iloc[0].input} matters most, then {imp.iloc[1].input.lower()}. Correlated inputs split credit. Bars: ±1 sd over 5 shuffles.")
save(fig, "feature_importance", height=720)'''),
    ("code", '''t["ape_base"] = 100 * (t.demand_lag_168 - y).abs() / y
s = t.groupby("season")[["ape_base", "ape", "ape_ercot"]].mean().loc[["Winter", "Spring", "Summer", "Fall"]]
fig = go.Figure()
for i, (col, name) in enumerate([("ape_base", "Baseline (last week)"), ("ape", "Mine (9:30 am information)"), ("ape_ercot", "ERCOT 9:30 am posting")]):
    fig.add_bar(x=s.index, y=s[col], name=name, marker_color=SERIES[i], hovertemplate=name + " · %{x}: %{y:.2f}%<extra></extra>")
fig.update_layout(title="Forecast error by season, test set 2024–2025", barmode="group", bargap=0.35, bargroupgap=0.08,
                  yaxis_title="Mean absolute % error", xaxis_title="Season")
add_caption(fig, "All three use only information available at 9:30 am the day before. Winter is the hardest season for each.")
save(fig, "model_error_by_season")
s.round(2)'''),
    ("md", "## The 10 biggest misses"),
    ("code", '''names = pd.read_parquet("data/clean/us_holidays.parquet")
names = dict(zip(pd.to_datetime(names.holiday_date), names.holiday_name))
t["err"] = t.pred - t.demand_mwh
miss = t.groupby("op_date").agg(mine=("ape", "mean"), ercot=("ape_ercot", "mean"), mean_error_gw=("err", lambda e: e.mean() / 1000),
                                tmin=("avg_temp_c", "min"), tmax=("avg_temp_c", "max"), fc_error=("fc_temp", "mean"), obs=("avg_temp_c", "mean"))
miss["temp_forecast_miss_c"] = miss.fc_error - miss.obs
worst = miss.sort_values("mine", ascending=False).head(10).drop(columns=["fc_error", "obs"]).round(1)
worst["holiday"] = [names.get(d, "") for d in worst.index]
worst.to_csv("data/clean/op_biggest_misses.csv")
t[["period", "op_date", "he", "season", "demand_mwh", "pred", "ercot_api_mwh", "ape", "ape_ercot"]].to_parquet("data/clean/op_test_predictions.parquet", index=False)
worst'''),
])

# ---------------------------------------------------------------- 07 prices
build("07_prices.ipynb", [
    ("md", '''# 07 · What the grid's changes are worth: day-ahead prices
Hourly day-ahead settlement prices from ERCOT's public report NP4-180-ER, 2019 to 2025. `HB_BUSAVG` is the average across the hubs' buses. Uri (Feb 10–20 2021) is excluded from the yearly tables and studied separately.'''),
    ("code", SETUP + '''
import plotly.graph_objects as go
from viz import add_caption, save, SERIES, INK
p = pd.read_parquet("data/raw/ercot_dam_prices.parquet")
p["d"] = pd.to_datetime(p.delivery_date)
p = p[~p.repeated_hour]
uri = p.d.between("2021-02-10", "2021-02-20")
P = p[(p.hub == "HB_BUSAVG") & ~uri].pivot_table(index="d", columns="hour_ending", values="price_usd_mwh")
print(P.shape, "days x hours")'''),
    ("md", "## The evening premium\nMedians, because a few scarcity days dominate the means. Midday is hours ending 11 am to 3 pm and evening is hours ending 7 to 9 pm. The spread is the top two hours minus the bottom two hours each day, a rough gross margin per MWh for a two-hour battery before losses."),
    ("code", '''def table(frame):
    srt = np.sort(frame.dropna().values, axis=1)
    return pd.DataFrame({"midday": frame.loc[:, 11:15].mean(axis=1).groupby(frame.index.year).median(),
                         "evening": frame.loc[:, 19:21].mean(axis=1).groupby(frame.index.year).median(),
                         "daily spread": pd.Series(srt[:, -2:].mean(axis=1) - srt[:, :2].mean(axis=1), index=frame.dropna().index).groupby(frame.dropna().index.year).median()})
annual, spring = table(P), table(P[P.index.month.isin([3, 4, 5])])
annual["evening premium"], spring["evening premium"] = annual.evening - annual.midday, spring.evening - spring.midday
annual.round(1).to_csv("data/clean/price_premium_annual.csv"); spring.round(1).to_csv("data/clean/price_premium_spring.csv")
display(annual.round(1)); spring.round(1)'''),
    ("code", '''fig = go.Figure()
for i, (col, name) in enumerate([("evening", "Evening, 7 to 9 pm"), ("midday", "Midday, 11 am to 3 pm")]):
    fig.add_scatter(x=spring.index, y=spring[col], mode="lines+markers", name=name, line=dict(color=SERIES[i], width=2.5), marker=dict(size=8),
                    hovertemplate=name + " · %{x}: $%{y:.0f}/MWh<extra></extra>")
    fig.add_annotation(x=2025, y=spring[col].iloc[-1], text=f"{name.split(',')[0]} ${spring[col].iloc[-1]:.0f}", showarrow=False, xanchor="left", xshift=8, font=dict(color=INK))
fig.update_layout(title="Spring day-ahead prices: evenings have pulled away from midday", xaxis_title="Year", yaxis_title="Median price ($/MWh)",
                  xaxis=dict(tickvals=list(range(2019, 2026)), range=[2018.7, 2026.1]), yaxis=dict(rangemode="tozero"), margin=dict(r=130))
add_caption(fig, f"The spring evening premium rose from {spring['evening premium'][2019]:.1f} to {spring['evening premium'][2025]:.1f} dollars per MWh. 2022 reflects high gas prices. HB_BUSAVG, March to May medians.")
save(fig, "evening_premium")'''),
    ("md", "## Winter Storm Uri at day-ahead prices\nDay-ahead price times served demand. This is a measure of market value, not what customers paid: hedges, real-time settlement, and later securitization all change the final bill."),
    ("code", '''b = p[p.hub == "HB_BUSAVG"]
d = q("SELECT local_ts, local_hour, demand_mwh FROM model_hourly")
d["local_ts"] = pd.to_datetime(d.local_ts)
d["d"] = (d.local_ts - pd.Timedelta(hours=1)).dt.normalize(); d["hour_ending"] = d.local_hour.replace(0, 24)
m = d.merge(b, on=["d", "hour_ending"]); m["value"] = m.demand_mwh * m.price_usd_mwh
yearly = (m.groupby(m.d.dt.year).value.sum() / 1e9).round(1).rename("$bn")
u = m[m.d.between("2021-02-14", "2021-02-19")]
before = m[m.d.between("2021-01-20", "2021-02-09")]
print(f"Feb 14-19 2021: ${u.value.sum() / 1e9:.1f}bn on {u.demand_mwh.sum() / 1000:,.0f} GWh, average ${u.value.sum() / u.demand_mwh.sum():,.0f}/MWh, max ${u.price_usd_mwh.max():,.0f}")
print(f"Jan 20-Feb 9 2021 average: ${before.value.sum() / before.demand_mwh.sum():.2f}/MWh")
yearly'''),
    ("md", "## West Texas: from cheap power to a premium\nWest hub minus North hub. Through 2022 West was cheaper, as wind crowded export lines. If local load outgrows the wires, the sign flips."),
    ("code", '''h = p[~uri].pivot_table(index=["d", "hour_ending"], columns="hub", values="price_usd_mwh")
gap = h.HB_WEST - h.HB_NORTH
yrs = gap.index.get_level_values(0).year
west = pd.DataFrame({"West minus North ($/MWh)": gap.groupby(yrs).mean(), "% of hours West is $5+ above North": 100 * (gap > 5).groupby(yrs).mean()}).round(1)
west.to_csv("data/clean/west_hub_gap.csv")
west'''),
])
print("built")
