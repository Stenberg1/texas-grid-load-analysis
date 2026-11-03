-- Question: how steep is the evening ramp in net load (demand minus wind and solar), and is it getting steeper? The duck curve.
SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE net_load_ramps AS
WITH net AS (
    SELECT period, local_ts, local_date, local_hour, year,
           demand_mwh, solar_mwh, wind_mwh,
           demand_mwh - wind_mwh - solar_mwh AS net_load_mwh
    FROM model_hourly
),
ramps AS (
    SELECT *,
           net_load_mwh - LAG(net_load_mwh, 3) OVER (ORDER BY period) AS ramp_3h_mwh
    FROM net
)
SELECT * FROM ramps;

-- Biggest 3-hour evening ramps (ending 5-10 pm local, around sunset), ranked within each year
CREATE OR REPLACE TABLE top_evening_ramps AS
SELECT * FROM (
    SELECT year, local_ts, net_load_mwh, ramp_3h_mwh,
           RANK() OVER (PARTITION BY year ORDER BY ramp_3h_mwh DESC) AS ramp_rank
    FROM net_load_ramps
    WHERE local_hour BETWEEN 17 AND 22
      AND year BETWEEN 2019 AND 2025
      AND ramp_3h_mwh IS NOT NULL
)
WHERE ramp_rank <= 10
ORDER BY year, ramp_rank;

-- Yearly summary: largest single ramp and average daily max evening ramp
CREATE OR REPLACE TABLE evening_ramp_yearly AS
WITH daily AS (
    SELECT year, local_date, MAX(ramp_3h_mwh) AS daily_max_ramp
    FROM net_load_ramps
    WHERE local_hour BETWEEN 17 AND 22 AND year BETWEEN 2019 AND 2025
    GROUP BY year, local_date
)
SELECT year,
       ROUND(AVG(daily_max_ramp)) AS avg_daily_max_ramp_mwh,
       ROUND(MAX(daily_max_ramp)) AS max_ramp_mwh
FROM daily
GROUP BY year
ORDER BY year;
