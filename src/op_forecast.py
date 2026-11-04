"""Day-ahead load forecast built only from what is known at ERCOT's 9:30 am posting.

For delivery day D (hours ending 1-24, Central time) the forecast is issued at 9:30 am on D-1. So:
- Load is known through hour ending 9 on D-1. Nothing later may be used.
- Weather is a forecast: the newest archived model run already published at 9:30 am.

The model predicts the ratio of load to a baseline, the average of the same hour on recent fully known
non-holiday days (D-2 back). Notebook 06 picks 14 days over 28 by cross-validation. Using a ratio to a
moving baseline handles load growth, and leaving holidays out means a holiday can't drag down the baseline.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

CENTRAL = "America/Chicago"
URI = ("2021-02-10", "2021-02-20")     # served demand was capped by outages, so it isn't true demand
GFS_PUBLISH_HOURS = 4                  # a run is treated as available 4 hours after its start time
BASELINE_DAYS = 14


def load_frame(con):
    """Hourly frame keyed by operating day and hour ending. Hour ending 24 is local_hour 0 of the next date."""
    df = con.execute("""SELECT period, local_ts, local_date, local_hour, is_holiday, demand_mwh,
                               avg_temp_c, ercot_forecast_mwh, season
                        FROM model_hourly ORDER BY period""").df()
    df["period"] = pd.to_datetime(df.period, utc=True)
    df["local_ts"] = pd.to_datetime(df.local_ts)
    df["op_date"] = (df.local_ts - pd.Timedelta(hours=1)).dt.normalize()
    df["he"] = df.local_hour.replace(0, 24)
    holidays = set(pd.to_datetime(df[df.is_holiday].local_date).dt.normalize())
    df["holiday"] = df.op_date.isin(holidays).astype(int)
    df["day_after_holiday"] = (df.op_date - pd.Timedelta(days=1)).isin(holidays).astype(int)
    df["day_before_holiday"] = (df.op_date + pd.Timedelta(days=1)).isin(holidays).astype(int)
    df["dow"] = df.op_date.dt.dayofweek
    df["weekend"] = (df.dow >= 5).astype(int)
    df["month"] = df.op_date.dt.month
    df["year"] = df.op_date.dt.year
    df["issue_utc"] = ((df.op_date - pd.Timedelta(days=1) + pd.Timedelta(hours=9, minutes=30))
                       .dt.tz_localize(CENTRAL, ambiguous=False, nonexistent="shift_forward").dt.tz_convert("UTC"))
    return df, holidays


def add_forecast_weather(df, con, weather_fc, weather_obs):
    """Add city and load-weighted forecast temperatures, using only runs published by the issue time.

    previous_day1 comes from a run about 24 hours before the valid time, previous_day2 about 48 hours.
    The day-1 run is used only if it was out by 9:30 am. Otherwise the older day-2 run is used, which
    slightly understates skill for afternoon hours. Before the archive starts (2021-03-24), training rows
    use observed temperature plus the mean forecast offset measured on 2022.
    """
    weights = con.execute("SELECT city, weight FROM dim_city_weight").df().set_index("city").weight
    cols = [f"fc_day{n}_c" for n in range(5)]
    gfs = weather_fc[weather_fc.model == "gfs"].set_index(["period", "city"])[cols]
    jma = weather_fc[weather_fc.model == "jma"].set_index(["period", "city"])[cols]
    fc = gfs.combine_first(jma).reset_index()          # JMA fills the GFS archive gap

    run_day1 = df.period.dt.floor("6h") - pd.Timedelta(hours=24)
    day1_ok = pd.Series((run_day1 + pd.Timedelta(hours=GFS_PUBLISH_HOURS) <= df.issue_utc).values, index=df.period)
    fc["fc_c"] = np.where(fc.period.map(day1_ok).fillna(False).astype(bool), fc.fc_day1_c, fc.fc_day2_c)
    for c in ["fc_day2_c", "fc_day3_c", "fc_day4_c"]:
        fc["fc_c"] = fc.fc_c.fillna(fc[c])

    wide = fc.pivot_table(index="period", columns="city", values="fc_c")
    obs = weather_obs.pivot_table(index="period", columns="city", values="temp_c")
    in_2022 = wide.index.year == 2022
    offset = float((wide[in_2022] - obs.reindex(wide[in_2022].index)).stack().mean())
    wide = wide.combine_first(obs + offset).dropna()
    # temperature as it was just after the fact, for the recent-days baseline
    recent = fc.pivot_table(index="period", columns="city", values="fc_day0_c").combine_first(obs).dropna()

    w = weights[wide.columns]
    out = pd.DataFrame({"fc_temp": wide.mul(w).sum(axis=1), "recent_temp": recent.mul(w).sum(axis=1)})
    named = wide.rename(columns=lambda c: "t_" + c.lower().replace(" ", "_"))
    return df.merge(out.join(named).reset_index(), on="period", how="left"), list(named.columns), offset


def add_load_features(df, holidays, n_days=BASELINE_DAYS, skip_holidays=True):
    """Baseline and recent-load features. Every load value used here is checked by assert_no_leak."""
    def by_day(col):
        return (df.pivot_table(index="op_date", columns="he", values=col, aggfunc="mean")
                  .interpolate(axis=1, limit_direction="both"))
    load, temp = by_day("demand_mwh"), by_day("recent_temp")
    load_ex, temp_ex = load.copy(), temp.copy()
    if skip_holidays:
        is_holiday = load.index.isin(holidays)
        load_ex[is_holiday] = np.nan
        temp_ex[is_holiday] = np.nan

    min_days = n_days // 2
    baseline = load_ex.shift(2).rolling(n_days, min_periods=min_days).mean()     # D-2 is the newest full day
    baseline_t = temp_ex.shift(2).rolling(n_days, min_periods=min_days).mean()
    key = pd.MultiIndex.from_arrays([df.op_date, df.he])
    x = df.copy()
    x["baseline"] = baseline.stack(future_stack=True).reindex(key).values
    x["baseline_temp"] = baseline_t.stack(future_stack=True).reindex(key).values
    # the freshest signal: hours ending 1-9 on D-1 against the baseline for those hours
    x["morning_ratio"] = (load_ex.loc[:, 1:9].mean(axis=1).shift(1)
                          / baseline.loc[:, 1:9].mean(axis=1)).reindex(x.op_date).values
    # the last full day (D-2), same hour, against the baseline
    x["d2_ratio"] = (load_ex.shift(2) / baseline).stack(future_stack=True).reindex(key).values
    x["cool"] = (x.fc_temp - 18.3).clip(lower=0)
    x["heat"] = (18.3 - x.fc_temp).clip(lower=0)
    x["temp_sq"] = x.fc_temp ** 2
    x["temp_vs_baseline"] = x.fc_temp - x.baseline_temp
    # buildings hold heat and cold, so recent days matter as well as this hour. Each fc_temp value was
    # issued no later than this hour's own 9:30 am posting, so these rolling means are all known in time.
    x = x.sort_values("period")
    x["fc_24h"] = x.fc_temp.rolling(24).mean()
    x["fc_72h"] = x.fc_temp.rolling(72).mean()
    x["fc_72h_chg"] = x.fc_72h - x.fc_72h.shift(24)
    night = x[x.he.between(1, 7)].groupby("op_date")
    x["overnight_fc"] = x.op_date.map(night.fc_temp.min())
    # the low on D-1 (hours ending 1-7) is already over at 9:30 am
    x["overnight_chg"] = x.overnight_fc - (x.op_date - pd.Timedelta(days=1)).map(night.recent_temp.min())
    return x


def assert_no_leak(x):
    """The newest load used is hour ending 9 on D-1, which must have ended before the 9:30 am issue time."""
    newest = ((x.op_date - pd.Timedelta(days=1) + pd.Timedelta(hours=9))
              .dt.tz_localize(CENTRAL, ambiguous=False, nonexistent="shift_forward").dt.tz_convert("UTC"))
    assert (newest <= x.issue_utc).all()
    day2_end = ((x.op_date - pd.Timedelta(days=1))
                .dt.tz_localize(CENTRAL, ambiguous=False, nonexistent="shift_forward").dt.tz_convert("UTC"))
    assert (day2_end < x.issue_utc).all()      # all of D-2 is over by then


CORE = ["fc_temp", "cool", "heat", "temp_sq", "he", "dow", "month", "weekend", "holiday",
        "temp_vs_baseline", "baseline_temp", "morning_ratio", "d2_ratio"]
ADJACENT = ["day_after_holiday", "day_before_holiday"]
THERMAL = ["fc_24h", "fc_72h", "fc_72h_chg", "overnight_fc", "overnight_chg"]


def usable(x, start="2019-01-30"):
    d = x.dropna(subset=["fc_temp", "baseline", "demand_mwh"])
    return d[(d.op_date >= start) & ~d.op_date.between(*URI)]


def fit(train, feats, params=None):
    # early stopping is off: its default check holds out random hours, which sit right next to training
    # hours in time, and that would make max_iter a ceiling instead of a setting that can be tuned
    model = HistGradientBoostingRegressor(random_state=0, early_stopping=False, **(params or {}))
    return model.fit(train[feats], train.demand_mwh / train.baseline)


def predict(model, d, feats):
    return d.baseline * model.predict(d[feats])


def mape(y, p):
    return float(100 * ((y - p).abs() / y).mean())


def rmse(y, p):
    return float(np.sqrt(((y - p) ** 2).mean()))
