-- Question: what does the warehouse look like? Loads raw parquet into raw_*, builds dim_fuel, dim_calendar, and fact tables.
SET TimeZone = 'UTC';

-- Raw layer: exact copies of the pulled files
CREATE OR REPLACE TABLE raw_demand     AS SELECT * FROM read_parquet('data/raw/ercot_demand.parquet');
CREATE OR REPLACE TABLE raw_generation AS SELECT * FROM read_parquet('data/raw/ercot_generation.parquet');
CREATE OR REPLACE TABLE raw_weather    AS SELECT * FROM read_parquet('data/raw/weather.parquet');
CREATE OR REPLACE TABLE raw_holidays   AS SELECT * FROM read_parquet('data/clean/us_holidays.parquet');

-- Fuel dimension
CREATE OR REPLACE TABLE dim_fuel (
    fueltype     VARCHAR PRIMARY KEY,
    fuel_name    VARCHAR,
    is_renewable BOOLEAN,
    is_storage   BOOLEAN
);
INSERT INTO dim_fuel VALUES
    ('NG',  'Natural gas',               FALSE, FALSE),
    ('COL', 'Coal',                      FALSE, FALSE),
    ('NUC', 'Nuclear',                   FALSE, FALSE),
    ('WND', 'Wind',                      TRUE,  FALSE),
    ('SUN', 'Solar',                     TRUE,  FALSE),
    ('WAT', 'Hydro',                     TRUE,  FALSE),
    ('OTH', 'Other',                     FALSE, FALSE),
    ('BAT', 'Battery storage',           FALSE, TRUE),
    ('UES', 'Unknown energy storage',    FALSE, TRUE);

-- Calendar dimension: one row per UTC hour, with Central-time attributes
CREATE OR REPLACE TABLE dim_calendar AS
WITH hours AS (
    SELECT ts AS period
    FROM generate_series(TIMESTAMPTZ '2019-01-01 00:00:00+00',
                         TIMESTAMPTZ '2025-12-31 23:00:00+00',
                         INTERVAL 1 HOUR) AS t(ts)
),
local AS (
    SELECT period, timezone('America/Chicago', period) AS local_ts FROM hours
)
SELECT
    l.period,
    l.local_ts,
    CAST(l.local_ts AS DATE)              AS local_date,
    hour(l.local_ts)                      AS local_hour,
    isodow(l.local_ts)                    AS day_of_week,      -- 1 = Monday
    month(l.local_ts)                     AS month,
    year(l.local_ts)                      AS year,
    CASE WHEN month(l.local_ts) IN (12, 1, 2) THEN 'Winter'
         WHEN month(l.local_ts) IN (3, 4, 5)  THEN 'Spring'
         WHEN month(l.local_ts) IN (6, 7, 8)  THEN 'Summer'
         ELSE 'Fall' END                  AS season,
    isodow(l.local_ts) >= 6               AS is_weekend,
    h.holiday_date IS NOT NULL            AS is_holiday
FROM local l
LEFT JOIN raw_holidays h ON h.holiday_date = CAST(l.local_ts AS DATE);

-- Fact tables (cleaned versions are rebuilt in 02_quality.sql)
CREATE OR REPLACE TABLE fact_load AS
SELECT period, demand_mwh, FALSE AS is_imputed FROM raw_demand;

CREATE OR REPLACE TABLE fact_generation AS
SELECT period, fueltype, generation_mwh, FALSE AS is_reclassified FROM raw_generation;

CREATE OR REPLACE TABLE fact_weather AS
SELECT period, city, temp_c FROM raw_weather;
