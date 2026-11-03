-- Question: what stable read-only interfaces does the notebook use? Views for daily peaks, yearly fuel mix, and hourly net load.
SET TimeZone = 'UTC';

CREATE OR REPLACE VIEW daily_peak AS
SELECT local_date, year, month, season,
       MAX(demand_mwh) AS peak_demand_mwh,
       AVG(demand_mwh) AS avg_demand_mwh,
       MAX(avg_temp_c) AS max_temp_c,
       MIN(avg_temp_c) AS min_temp_c
FROM model_hourly
GROUP BY local_date, year, month, season;

CREATE OR REPLACE VIEW fuel_mix_yearly AS
SELECT c.year, f.fueltype, f.fuel_name, f.is_renewable,
       SUM(g.generation_mwh) AS generation_mwh,
       100.0 * SUM(g.generation_mwh)
             / SUM(SUM(g.generation_mwh)) FILTER (WHERE NOT f.is_storage) OVER (PARTITION BY c.year) AS share_pct
FROM fact_generation g
JOIN dim_fuel f USING (fueltype)
JOIN dim_calendar c USING (period)
WHERE c.year BETWEEN 2019 AND 2025
GROUP BY c.year, f.fueltype, f.fuel_name, f.is_renewable, f.is_storage;

CREATE OR REPLACE VIEW net_load_hourly AS
SELECT period, local_ts, local_date, local_hour, year,
       demand_mwh, wind_mwh, solar_mwh, net_load_mwh, ramp_3h_mwh
FROM net_load_ramps;
