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
