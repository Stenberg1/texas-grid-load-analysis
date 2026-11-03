-- Question: how accurate is ERCOT's own day-ahead load forecast, by year, season and hour?
SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE ercot_forecast_error AS
SELECT period, local_ts, local_hour, year, season, is_holiday,
       demand_mwh, ercot_forecast_mwh,
       ercot_forecast_mwh - demand_mwh                         AS error_mwh,
       100.0 * ABS(ercot_forecast_mwh - demand_mwh) / demand_mwh AS ape_pct
FROM model_hourly
WHERE ercot_forecast_mwh IS NOT NULL AND demand_mwh IS NOT NULL;

CREATE OR REPLACE TABLE ercot_forecast_yearly AS
SELECT year,
       ROUND(SQRT(AVG(error_mwh * error_mwh))) AS rmse_mwh,
       ROUND(AVG(ape_pct), 2)                  AS mape_pct,
       ROUND(AVG(error_mwh))                   AS bias_mwh,   -- positive = over-forecast
       COUNT(*)                                AS hours
FROM ercot_forecast_error
WHERE year BETWEEN 2019 AND 2025
GROUP BY year
ORDER BY year;

-- ERCOT API forecasts (09:30 posting the day before), 2024-2025: accuracy of each forecast model
-- on the hours it covers (model X only starts partway through), and of the model ERCOT flagged as in use.
CREATE OR REPLACE TABLE ercot_model_accuracy AS
WITH scored AS (
    SELECT f.period, f.model, f.in_use, f.system_total_mwh - l.demand_mwh AS err, l.demand_mwh
    FROM fact_ercot_forecast_model f
    JOIN fact_load l USING (period)
),
labelled AS (
    SELECT model AS forecast, err, demand_mwh, period FROM scored
    UNION ALL
    SELECT 'In use (ERCOT''s daily pick)', err, demand_mwh, period FROM scored WHERE in_use
)
SELECT forecast,
       ROUND(100 * AVG(ABS(err) / demand_mwh), 2) AS mape_pct,
       ROUND(SQRT(AVG(err * err)))                AS rmse_mwh,
       ROUND(AVG(err))                            AS bias_mwh,
       COUNT(*)                                   AS hours,
       MIN(CAST(timezone('America/Chicago', period) AS DATE)) AS first_day
FROM labelled
GROUP BY forecast
ORDER BY mape_pct;

-- How often each model was the one in use (ERCOT can switch models within a day, so count hours)
CREATE OR REPLACE TABLE ercot_model_in_use AS
SELECT model, COUNT(*) AS hours_in_use,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_hours
FROM fact_ercot_forecast_model WHERE in_use GROUP BY model ORDER BY hours_in_use DESC;

-- Zone-level accuracy of the in-use forecast vs EIA zone load (zones unpivoted with UNPIVOT)
CREATE OR REPLACE TABLE ercot_zone_accuracy AS
WITH f AS (
    UNPIVOT (SELECT period, coast, east, far_west, north, north_central, south_central, southern, west
             FROM fact_ercot_forecast_model WHERE in_use)
    ON coast, east, far_west, north, north_central, south_central, southern, west
    INTO NAME zone_name VALUE forecast_mwh
),
zmap AS (
    SELECT * FROM (VALUES ('coast','COAS'), ('east','EAST'), ('far_west','FWES'), ('north','NRTH'),
                          ('north_central','NCEN'), ('south_central','SCEN'), ('southern','SOUT'), ('west','WEST'))
           AS t(zone_name, zone)
),
ok_hours AS (   -- only hours where the 8 zones add up to ERCOT total (see qa_zone_mismatch)
    SELECT DISTINCT z.period FROM fact_zone_load z
    WHERE z.period NOT IN (SELECT period FROM qa_zone_mismatch)
)
SELECT m.zone, f.zone_name,
       ROUND(100 * AVG(ABS(f.forecast_mwh - z.demand_mwh) / z.demand_mwh), 2) AS mape_pct,
       ROUND(AVG(z.demand_mwh)) AS avg_load_mwh,
       COUNT(*) AS hours
FROM f
JOIN zmap m USING (zone_name)
JOIN fact_zone_load z ON z.period = f.period AND z.zone = m.zone
JOIN ok_hours o ON o.period = f.period
GROUP BY m.zone, f.zone_name
ORDER BY mape_pct;
