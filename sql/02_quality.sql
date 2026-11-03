-- Question: is the data complete and sane? Logs missing hours, duplicates and outliers into qa_* tables, then applies documented fixes.
SET TimeZone = 'UTC';

-- 1. Missing demand hours: every expected hour LEFT JOINed to fact_load
CREATE OR REPLACE TABLE qa_missing_demand AS
SELECT c.period, c.local_ts
FROM dim_calendar c
LEFT JOIN fact_load f USING (period)
WHERE f.period IS NULL OR f.demand_mwh IS NULL;

-- 2. Missing generation hours (no rows for any fuel)
CREATE OR REPLACE TABLE qa_missing_generation AS
SELECT c.period, c.local_ts
FROM dim_calendar c
LEFT JOIN (SELECT DISTINCT period FROM fact_generation) g USING (period)
WHERE g.period IS NULL;

-- 2b. Missing ERCOT forecast hours
CREATE OR REPLACE TABLE qa_missing_forecast AS
SELECT c.period, c.local_ts
FROM dim_calendar c
LEFT JOIN fact_forecast f USING (period)
WHERE f.period IS NULL;

-- 2c. Hours where the 8 weather zones do not add up to ERCOT total demand (more than 2% off)
CREATE OR REPLACE TABLE qa_zone_mismatch AS
WITH z AS (SELECT period, SUM(demand_mwh) AS zone_sum, COUNT(*) AS n_zones FROM fact_zone_load GROUP BY period)
SELECT z.period, z.n_zones, z.zone_sum, l.demand_mwh, z.zone_sum / l.demand_mwh AS ratio
FROM z JOIN fact_load l USING (period)
WHERE ABS(z.zone_sum / l.demand_mwh - 1) > 0.02;

-- 2d. Missing weather (any city, any hour)
CREATE OR REPLACE TABLE qa_missing_weather AS
SELECT c.period, ci.city
FROM dim_calendar c CROSS JOIN dim_city ci
LEFT JOIN fact_weather w ON w.period = c.period AND w.city = ci.city
WHERE w.temp_c IS NULL;

-- 3. Duplicates
CREATE OR REPLACE TABLE qa_duplicates AS
SELECT 'demand' AS tbl, period, NULL AS fueltype, COUNT(*) AS n
FROM fact_load GROUP BY period HAVING COUNT(*) > 1
UNION ALL
SELECT 'generation', period, fueltype, COUNT(*)
FROM fact_generation GROUP BY period, fueltype HAVING COUNT(*) > 1
UNION ALL
SELECT 'forecast', period, NULL, COUNT(*)
FROM fact_forecast GROUP BY period HAVING COUNT(*) > 1
UNION ALL
SELECT 'gas price', CAST(trade_date AS TIMESTAMPTZ), NULL, COUNT(*)
FROM fact_gas_price GROUP BY trade_date HAVING COUNT(*) > 1;

-- 4. Outliers and negatives
CREATE OR REPLACE TABLE qa_outliers AS
SELECT 'demand out of range' AS issue, period, NULL AS fueltype, demand_mwh AS value
FROM fact_load WHERE demand_mwh < 0 OR demand_mwh > 100000
UNION ALL
SELECT 'negative wind/solar', period, fueltype, generation_mwh
FROM fact_generation WHERE fueltype IN ('SUN', 'WND') AND generation_mwh < 0
UNION ALL
SELECT 'OTH spike with gas near zero (gas misfiled as OTH)', g.period, g.fueltype, g.generation_mwh
FROM fact_generation g WHERE g.fueltype = 'OTH' AND g.generation_mwh > 5000
UNION ALL
SELECT 'forecast out of range', period, NULL, forecast_mwh
FROM fact_forecast WHERE forecast_mwh < 0 OR forecast_mwh > 100000
UNION ALL
SELECT 'gas price <= 0', CAST(trade_date AS TIMESTAMPTZ), NULL, price_usd_mmbtu
FROM fact_gas_price WHERE price_usd_mmbtu <= 0;

-- 5. Summary of checks
CREATE OR REPLACE TABLE qa_summary AS
SELECT 'missing demand hours' AS check_name, COUNT(*) AS n FROM qa_missing_demand
UNION ALL SELECT 'missing generation hours', COUNT(*) FROM qa_missing_generation
UNION ALL SELECT 'duplicate rows', COUNT(*) FROM qa_duplicates
UNION ALL SELECT 'demand < 0 or > 100,000 MWh', COUNT(*) FROM qa_outliers WHERE issue = 'demand out of range'
UNION ALL SELECT 'negative wind/solar', COUNT(*) FROM qa_outliers WHERE issue = 'negative wind/solar'
UNION ALL SELECT 'gas hours misfiled as OTH', COUNT(*) FROM qa_outliers WHERE issue LIKE 'OTH spike%'
UNION ALL SELECT 'missing ERCOT forecast hours', COUNT(*) FROM qa_missing_forecast
UNION ALL SELECT 'zone sum off total by >2% (hours)', COUNT(*) FROM qa_zone_mismatch
UNION ALL SELECT 'missing city-hour temperatures', COUNT(*) FROM qa_missing_weather
UNION ALL SELECT 'forecast < 0 or > 100,000 MWh', COUNT(*) FROM qa_outliers WHERE issue = 'forecast out of range'
UNION ALL SELECT 'gas price <= 0', COUNT(*) FROM qa_outliers WHERE issue = 'gas price <= 0';

-- FIX A: fill missing demand hours by time-weighted linear interpolation between the nearest
--        known hours (correct for gaps of any length), flagged is_imputed
CREATE OR REPLACE TABLE fact_load AS
WITH spine AS (
    SELECT c.period, f.demand_mwh
    FROM dim_calendar c LEFT JOIN fact_load f USING (period)
),
nb AS (
    SELECT period, demand_mwh,
           LAST_VALUE(demand_mwh IGNORE NULLS) OVER w_prev AS prev_v,
           LAST_VALUE(CASE WHEN demand_mwh IS NOT NULL THEN period END IGNORE NULLS) OVER w_prev AS prev_t,
           FIRST_VALUE(demand_mwh IGNORE NULLS) OVER w_next AS next_v,
           FIRST_VALUE(CASE WHEN demand_mwh IS NOT NULL THEN period END IGNORE NULLS) OVER w_next AS next_t
    FROM spine
    WINDOW w_prev AS (ORDER BY period ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
           w_next AS (ORDER BY period ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING)
)
SELECT period,
       COALESCE(demand_mwh,
                prev_v + (next_v - prev_v) * epoch(period - prev_t) / epoch(next_t - prev_t)) AS demand_mwh,
       demand_mwh IS NULL AS is_imputed
FROM nb;

-- FIX B: move misfiled gas back from OTH to NG for the flagged hours
CREATE OR REPLACE TABLE fact_generation AS
WITH bad AS (SELECT period, value AS oth_mwh FROM qa_outliers WHERE issue LIKE 'OTH spike%')
SELECT g.period, g.fueltype,
       CASE WHEN b.period IS NOT NULL AND g.fueltype = 'NG'  THEN g.generation_mwh + b.oth_mwh
            WHEN b.period IS NOT NULL AND g.fueltype = 'OTH' THEN 0
            ELSE g.generation_mwh END AS generation_mwh,
       b.period IS NOT NULL AND g.fueltype IN ('NG', 'OTH') AS is_reclassified
FROM fact_generation g
LEFT JOIN bad b USING (period);
-- Missing generation hours (Dec 5 2025) and missing forecast hours (Dec 5-7 2025) are left NULL:
-- no neighbour-based guess is good for a full day, and forecast comparisons drop those hours.
