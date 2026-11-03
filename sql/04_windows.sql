-- Question: how does load trend, ramp and grow? Rolling averages, ramps, lag features, YoY peak growth and top peak hours via window functions.
SET TimeZone = 'UTC';

-- Rolling 7-day average, hour-over-hour ramp, and day-ahead lag features.
-- dim_calendar guarantees one row per hour, so ROWS offsets equal hours.
CREATE OR REPLACE TABLE model_hourly AS
SELECT *,
       AVG(demand_mwh) OVER (ORDER BY period ROWS BETWEEN 167 PRECEDING AND CURRENT ROW) AS demand_7d_avg,
       demand_mwh - LAG(demand_mwh, 1) OVER (ORDER BY period)                            AS ramp_1h,
       LAG(demand_mwh, 24)  OVER (ORDER BY period)                                       AS demand_lag_24,
       LAG(demand_mwh, 168) OVER (ORDER BY period)                                       AS demand_lag_168,
       LAG(avg_temp_c, 24)  OVER (ORDER BY period)                                       AS temp_lag_24
FROM model_hourly
ORDER BY period;

-- Year-over-year peak growth
CREATE OR REPLACE TABLE peak_growth_yearly AS
WITH yearly AS (
    SELECT year, MAX(demand_mwh) AS peak_mwh
    FROM model_hourly
    WHERE year BETWEEN 2019 AND 2025
    GROUP BY year
)
SELECT year, peak_mwh,
       peak_mwh - LAG(peak_mwh) OVER (ORDER BY year) AS peak_change_mwh,
       ROUND(100.0 * (peak_mwh - LAG(peak_mwh) OVER (ORDER BY year)) / LAG(peak_mwh) OVER (ORDER BY year), 2) AS peak_growth_pct
FROM yearly
ORDER BY year;

-- Top 20 peak hours per year
CREATE OR REPLACE TABLE top_peaks_yearly AS
SELECT * FROM (
    SELECT year, period, local_ts, demand_mwh, avg_temp_c,
           RANK() OVER (PARTITION BY year ORDER BY demand_mwh DESC) AS peak_rank
    FROM model_hourly
    WHERE year BETWEEN 2019 AND 2025
)
WHERE peak_rank <= 20
ORDER BY year, peak_rank;
