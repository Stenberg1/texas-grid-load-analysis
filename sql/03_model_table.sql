-- Question: what does one clean row per hour look like? Joins demand, pivoted generation, and average temperature onto the calendar.
SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE model_hourly AS
WITH demand AS (
    SELECT period, demand_mwh, is_imputed FROM fact_load
),
gen AS (
    SELECT period,
           CAST(SUM(CASE WHEN fueltype = 'SUN' THEN generation_mwh END) AS DOUBLE) AS solar_mwh,
           CAST(SUM(CASE WHEN fueltype = 'WND' THEN generation_mwh END) AS DOUBLE) AS wind_mwh,
           CAST(SUM(CASE WHEN fueltype = 'NG'  THEN generation_mwh END) AS DOUBLE) AS gas_mwh,
           CAST(SUM(CASE WHEN fueltype = 'COL' THEN generation_mwh END) AS DOUBLE) AS coal_mwh,
           CAST(SUM(CASE WHEN fueltype = 'NUC' THEN generation_mwh END) AS DOUBLE) AS nuclear_mwh,
           CAST(SUM(CASE WHEN fueltype = 'WAT' THEN generation_mwh END) AS DOUBLE) AS hydro_mwh,
           CAST(SUM(CASE WHEN fueltype = 'OTH' THEN generation_mwh END) AS DOUBLE) AS other_mwh,
           CAST(SUM(CASE WHEN fueltype IN ('BAT', 'UES') THEN generation_mwh END) AS DOUBLE) AS storage_mwh,
           CAST(SUM(generation_mwh) AS DOUBLE) AS total_gen_mwh
    FROM fact_generation
    GROUP BY period
),
temp AS (
    -- avg_temp_c (used by the model) = load-weighted average of 8 cities (weights in dim_city_weight).
    -- The 4-city and plain 8-city averages are kept for comparison.
    SELECT w.period,
           SUM(w.temp_c * cw.weight)                                                        AS avg_temp_c,
           AVG(w.temp_c)                                                                    AS temp_8city_simple_c,
           AVG(CASE WHEN w.city IN ('Dallas', 'Houston', 'Austin', 'San Antonio') THEN w.temp_c END) AS temp_4city_c
    FROM fact_weather w
    JOIN dim_city_weight cw USING (city)
    GROUP BY w.period
),
gas_price AS (
    -- Henry Hub trades on weekdays only: ASOF JOIN carries the latest price across weekends/holidays
    SELECT d.local_date, g.price_usd_mmbtu AS henry_hub_usd
    FROM (SELECT DISTINCT local_date FROM dim_calendar) d
    ASOF LEFT JOIN fact_gas_price g ON d.local_date >= g.trade_date
)
SELECT
    c.period, c.local_ts, c.local_date, c.local_hour, c.day_of_week, c.month, c.year,
    c.season, c.is_weekend, c.is_holiday,
    d.demand_mwh, d.is_imputed,
    g.solar_mwh, g.wind_mwh, g.gas_mwh, g.coal_mwh, g.nuclear_mwh, g.hydro_mwh,
    g.other_mwh, g.storage_mwh, g.total_gen_mwh,
    t.avg_temp_c, t.temp_8city_simple_c, t.temp_4city_c,
    f.forecast_mwh AS ercot_forecast_mwh,
    gp.henry_hub_usd
FROM dim_calendar c
LEFT JOIN demand d USING (period)
LEFT JOIN gen    g USING (period)
LEFT JOIN temp   t USING (period)
LEFT JOIN fact_forecast f USING (period)
LEFT JOIN gas_price gp USING (local_date)
ORDER BY c.period;
