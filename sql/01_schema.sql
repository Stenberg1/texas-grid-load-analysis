-- Question: what does the warehouse look like? Loads raw parquet into raw_*, builds dim_fuel, dim_calendar, and fact tables.
SET TimeZone = 'UTC';

-- Raw layer: exact copies of the pulled files
CREATE OR REPLACE TABLE raw_demand     AS SELECT * FROM read_parquet('data/raw/ercot_demand.parquet');
CREATE OR REPLACE TABLE raw_generation AS SELECT * FROM read_parquet('data/raw/ercot_generation.parquet');
CREATE OR REPLACE TABLE raw_weather    AS SELECT * FROM read_parquet('data/raw/weather.parquet');
CREATE OR REPLACE TABLE raw_holidays   AS SELECT * FROM read_parquet('data/clean/us_holidays.parquet');
CREATE OR REPLACE TABLE raw_forecast   AS SELECT * FROM read_parquet('data/raw/ercot_forecast.parquet');
CREATE OR REPLACE TABLE raw_zone_load  AS SELECT * FROM read_parquet('data/raw/ercot_zone_load.parquet');
CREATE OR REPLACE TABLE raw_henry_hub  AS SELECT * FROM read_parquet('data/raw/henry_hub.parquet');

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

-- City dimension: each weather city mapped to the ERCOT weather zone it represents.
-- The North zone (NRTH, ~2.5% of load) has no city; weights are renormalised over the zones that do.
CREATE OR REPLACE TABLE dim_city (
    city      VARCHAR PRIMARY KEY,
    zone      VARCHAR,
    zone_name VARCHAR,
    latitude  DOUBLE,
    longitude DOUBLE
);
INSERT INTO dim_city VALUES
    ('Houston',        'COAS', 'Coast',         29.76,  -95.37),
    ('Dallas',         'NCEN', 'North Central', 32.78,  -96.80),
    ('Austin',         'SCEN', 'South Central', 30.27,  -97.74),
    ('San Antonio',    'SCEN', 'South Central', 29.42,  -98.49),
    ('Corpus Christi', 'SOUT', 'Southern',      27.80,  -97.40),
    ('Midland',        'FWES', 'Far West',      32.00, -102.08),
    ('Lubbock',        'WEST', 'West',          33.58, -101.85),
    ('Tyler',          'EAST', 'East',          32.35,  -95.30);

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

CREATE OR REPLACE TABLE fact_forecast AS
SELECT period, forecast_mwh FROM raw_forecast;

CREATE OR REPLACE TABLE fact_zone_load AS
SELECT period, zone, demand_mwh FROM raw_zone_load;

CREATE OR REPLACE TABLE fact_gas_price AS
SELECT date AS trade_date, price_usd_mmbtu FROM raw_henry_hub;

-- City temperature weights = share of zone load over the TRAINING period only (2019-05-27 to 2023-12-31),
-- split equally between cities that share a zone. Fixed constants, so no test-period information leaks in.
CREATE OR REPLACE TABLE dim_city_weight AS
WITH zone_share AS (
    SELECT zone, SUM(demand_mwh) AS zone_mwh
    FROM fact_zone_load
    WHERE period < TIMESTAMPTZ '2024-01-01 00:00:00+00'
    GROUP BY zone
),
mapped AS (
    SELECT c.city, c.zone, z.zone_mwh / COUNT(*) OVER (PARTITION BY c.zone) AS city_mwh
    FROM dim_city c JOIN zone_share z USING (zone)
)
SELECT city, zone, city_mwh / SUM(city_mwh) OVER () AS weight
FROM mapped;
