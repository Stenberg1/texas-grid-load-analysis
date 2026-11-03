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
**Limitation:** temperature is *observed* temperature standing in for a day-ahead weather forecast, so our error is optimistic. ERCOT's own forecast, which we compare against, had to use real weather forecasts.
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
FINAL_FEATURES = BASE_FEATURES + ["temp_delta_24"]'''),
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
    ("code", '''import plotly.graph_objects as go
from viz import add_caption, save, SERIES
fig = go.Figure()
for i, (col, name) in enumerate([("ape_baseline", "Baseline (last week)"), ("ape_best", best_name), ("ape_ercot", "ERCOT official forecast")]):
    fig.add_bar(x=by_season.index, y=by_season[col], name=name, marker_color=SERIES[i])
fig.update_layout(title="Forecast error by season, test set 2024–2025", barmode="group", bargap=0.35, bargroupgap=0.08,
                  yaxis_title="Mean absolute % error", xaxis_title="Season")
add_caption(fig, "Winter is the hardest season for every forecast: cold snaps (and holidays such as MLK Day during them) drive the biggest misses.")
save(fig, "model_error_by_season")'''),
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
    ("md", "## 2. Midday solar share by year"),
    ("code", '''s = q("SELECT * FROM midday_solar_share")
fig = go.Figure(go.Bar(x=s.year, y=s.midday_solar_pct, marker_color=SERIES[0], name="Midday solar share",
                       text=[f"{v:.1f}%" if y in (s.year.min(), s.year.max()) else "" for y, v in zip(s.year, s.midday_solar_pct)],
                       textposition="outside", textfont=dict(color=INK),
                       hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
fig.update_layout(title="Solar share of ERCOT generation, 11 am–3 pm local time", bargap=0.45,
                  xaxis_title="Year", yaxis_title="Share of midday generation (%)", xaxis=dict(dtick=1))
add_caption(fig, f"Solar went from {s.midday_solar_pct.iloc[0]:.1f}% to {s.midday_solar_pct.iloc[-1]:.1f}% of midday generation between {s.year.iloc[0]} and {s.year.iloc[-1]}.")
save(fig, "midday_solar_share")'''),
    ("md", "## 3. Peak load by year"),
    ("code", '''p = q("SELECT * FROM peak_growth_yearly")
rec = p.loc[p.peak_mwh.idxmax()]
fig = go.Figure(go.Bar(x=p.year, y=p.peak_mwh / 1000, marker_color=SERIES[0], name="Annual peak",
                       text=[f"{v/1000:.1f} GW" if y in (p.year.iloc[0], rec.year) else "" for y, v in zip(p.year, p.peak_mwh)],
                       textposition="outside", textfont=dict(color=INK),
                       hovertemplate="%{x}: %{y:.1f} GW<extra></extra>"))
fig.update_layout(title="ERCOT annual peak hourly load", bargap=0.45, xaxis_title="Year",
                  yaxis_title="Peak hourly load (GW)", yaxis=dict(range=[0, 95]), xaxis=dict(dtick=1))
growth = 100 * (rec.peak_mwh / p.peak_mwh.iloc[0] - 1)
add_caption(fig, f"Peak load rose {growth:.0f}% from {p.year.iloc[0]} to the {int(rec.year)} record of {rec.peak_mwh/1000:.1f} GW, nearly all of it in 2022–2023.")
save(fig, "peak_load_by_year")'''),
    ("md", "## 4. Net load and the duck curve\nAverage spring-day (March–May) net load profile, comparing three years."),
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
    ("md", "## 5. Winter Storm Uri"),
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
    ("md", "## 6. Model error by hour of day"),
    ("code", '''t = pd.read_parquet("data/clean/test_predictions.parquet")
res = pd.read_csv("data/clean/model_results.csv", index_col=0)
ours = [k for k in res.index if not k.startswith(("Baseline", "Reference", "ERCOT"))]
best = res.loc[ours, "MAPE (%)"].idxmin()
h = t.groupby("local_hour")[["ape_baseline", "ape_best", "ape_ercot"]].mean()
fig = go.Figure()
for i, (col, name, short) in enumerate([("ape_baseline", "Baseline: same hour last week", "Baseline"), ("ape_best", best, "Our model"),
                                        ("ape_ercot", "ERCOT official day-ahead forecast", "ERCOT")]):
    fig.add_scatter(x=h.index, y=h[col], mode="lines+markers", name=name, line=dict(color=SERIES[i], width=2.5),
                    marker=dict(size=8), hovertemplate=f"{short} · %{{x}}:00<br>%{{y:.2f}}%<extra></extra>")
    fig.add_annotation(x=23, y=h[col].iloc[-1], text=short, showarrow=False, xanchor="left", xshift=8, font=dict(color=INK))
fig.update_layout(title="Day-ahead forecast error by hour of day, test set 2024–2025",
                  xaxis_title="Hour ending (Central time)", yaxis_title="Mean absolute % error",
                  yaxis=dict(rangemode="tozero"), xaxis=dict(dtick=3, range=[-0.5, 25]))
add_caption(fig, f"Our model cuts the baseline's {res.loc['Baseline: same hour last week','MAPE (%)']:.1f}% error to {res.loc[best,'MAPE (%)']:.1f}%; ERCOT's official forecast does better still at {res.loc['ERCOT official day-ahead forecast','MAPE (%)']:.1f}%.")
save(fig, "model_error_by_hour")'''),
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
d = q("SELECT * FROM gas_daily WHERE NOT is_uri")
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
add_caption(fig, f"Fuel switching has faded: {first.shift_per_doubling_pts:+.1f} pts per doubling in {int(first.year)}, {late.shift_per_doubling_pts.min():+.1f} to {late.shift_per_doubling_pts.max():+.1f} since 2022 as coal shrank. Pooled: {b:+.1f} pts. Bars: 95% CI.")
save(fig, "gas_price_switching")'''),
])
print("built")
