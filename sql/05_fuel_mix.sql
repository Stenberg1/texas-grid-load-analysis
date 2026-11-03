-- Question: how has the generation mix changed, and how fast has midday solar grown? Yearly fuel shares and midday solar share.
SET TimeZone = 'UTC';

-- Yearly fuel shares of total generation (storage excluded from the denominator: it shifts energy, it does not generate it)
CREATE OR REPLACE TABLE fuel_share_yearly AS
WITH y AS (
    SELECT c.year,
           SUM(CASE WHEN g.fueltype = 'NG'  THEN g.generation_mwh END) AS gas,
           SUM(CASE WHEN g.fueltype = 'COL' THEN g.generation_mwh END) AS coal,
           SUM(CASE WHEN g.fueltype = 'NUC' THEN g.generation_mwh END) AS nuclear,
           SUM(CASE WHEN g.fueltype = 'WND' THEN g.generation_mwh END) AS wind,
           SUM(CASE WHEN g.fueltype = 'SUN' THEN g.generation_mwh END) AS solar,
           SUM(CASE WHEN g.fueltype IN ('WAT', 'OTH') THEN g.generation_mwh END) AS hydro_other,
           SUM(CASE WHEN NOT f.is_storage THEN g.generation_mwh END) AS total
    FROM fact_generation g
    JOIN dim_calendar c USING (period)
    JOIN dim_fuel f USING (fueltype)
    WHERE c.year BETWEEN 2019 AND 2025
    GROUP BY c.year
)
SELECT year,
       ROUND(100.0 * gas / total, 1)         AS gas_pct,
       ROUND(100.0 * coal / total, 1)        AS coal_pct,
       ROUND(100.0 * nuclear / total, 1)     AS nuclear_pct,
       ROUND(100.0 * wind / total, 1)        AS wind_pct,
       ROUND(100.0 * solar / total, 1)       AS solar_pct,
       ROUND(100.0 * hydro_other / total, 1) AS hydro_other_pct,
       ROUND(total / 1e6, 1)                 AS total_twh
FROM y
ORDER BY year;

-- Midday solar share: solar / total generation for local hours 11-15
CREATE OR REPLACE TABLE midday_solar_share AS
SELECT year,
       ROUND(100.0 * SUM(solar_mwh) / SUM(total_gen_mwh - COALESCE(storage_mwh, 0)), 1) AS midday_solar_pct,
       ROUND(AVG(solar_mwh)) AS avg_midday_solar_mwh,
       ROUND(MAX(solar_mwh)) AS max_solar_mwh
FROM model_hourly
WHERE local_hour BETWEEN 11 AND 15
  AND year BETWEEN 2019 AND 2025
  AND total_gen_mwh IS NOT NULL
GROUP BY year
ORDER BY year;
