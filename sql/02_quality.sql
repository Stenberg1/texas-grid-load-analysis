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

-- 3. Duplicates
CREATE OR REPLACE TABLE qa_duplicates AS
SELECT 'demand' AS tbl, period, NULL AS fueltype, COUNT(*) AS n
FROM fact_load GROUP BY period HAVING COUNT(*) > 1
UNION ALL
SELECT 'generation', period, fueltype, COUNT(*)
FROM fact_generation GROUP BY period, fueltype HAVING COUNT(*) > 1;

-- 4. Outliers and negatives
CREATE OR REPLACE TABLE qa_outliers AS
SELECT 'demand out of range' AS issue, period, NULL AS fueltype, demand_mwh AS value
FROM fact_load WHERE demand_mwh < 0 OR demand_mwh > 100000
UNION ALL
SELECT 'negative wind/solar', period, fueltype, generation_mwh
FROM fact_generation WHERE fueltype IN ('SUN', 'WND') AND generation_mwh < 0
UNION ALL
SELECT 'OTH spike with gas near zero (gas misfiled as OTH)', g.period, g.fueltype, g.generation_mwh
FROM fact_generation g WHERE g.fueltype = 'OTH' AND g.generation_mwh > 5000;

-- 5. Summary of checks
CREATE OR REPLACE TABLE qa_summary AS
SELECT 'missing demand hours' AS check_name, COUNT(*) AS n FROM qa_missing_demand
UNION ALL SELECT 'missing generation hours', COUNT(*) FROM qa_missing_generation
UNION ALL SELECT 'duplicate rows', COUNT(*) FROM qa_duplicates
UNION ALL SELECT 'demand < 0 or > 100,000 MWh', COUNT(*) FROM qa_outliers WHERE issue = 'demand out of range'
UNION ALL SELECT 'negative wind/solar', COUNT(*) FROM qa_outliers WHERE issue = 'negative wind/solar'
UNION ALL SELECT 'gas hours misfiled as OTH', COUNT(*) FROM qa_outliers WHERE issue LIKE 'OTH spike%';

-- FIX A: fill missing demand hours by linear interpolation between neighbours, flagged is_imputed
CREATE OR REPLACE TABLE fact_load AS
WITH spine AS (
    SELECT c.period, f.demand_mwh
    FROM dim_calendar c LEFT JOIN fact_load f USING (period)
),
nb AS (
    SELECT period, demand_mwh,
           LAST_VALUE(demand_mwh IGNORE NULLS) OVER (ORDER BY period ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_v,
           FIRST_VALUE(demand_mwh IGNORE NULLS) OVER (ORDER BY period ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_v
    FROM spine
)
SELECT period,
       COALESCE(demand_mwh, (prev_v + next_v) / 2.0) AS demand_mwh,
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
-- Missing generation hours (Dec 5 2025) are left NULL: no neighbours-based guess is good for a full day.
