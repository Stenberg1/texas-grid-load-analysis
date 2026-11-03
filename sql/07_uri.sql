-- Question: what happened during Winter Storm Uri (Feb 13-20 2021) versus a normal same-weekday, same-hour baseline from three weeks before the cold arrived, and how much load was shed?
SET TimeZone = 'UTC';

CREATE OR REPLACE TABLE uri_hourly AS
WITH baseline AS (
    -- three weeks before the cold arrived: Jan 20 - Feb 9 2021 (local), averaged by weekday and hour.
    -- (Feb 10-12 are excluded: temperatures were already near freezing and demand was 54-64 GW.)
    SELECT day_of_week, local_hour,
           AVG(demand_mwh) AS base_demand,
           AVG(gas_mwh)    AS base_gas,
           AVG(wind_mwh)   AS base_wind,
           AVG(coal_mwh)   AS base_coal,
           AVG(nuclear_mwh) AS base_nuclear,
           AVG(total_gen_mwh) AS base_total_gen,
           AVG(avg_temp_c) AS base_temp
    FROM model_hourly
    WHERE local_date BETWEEN DATE '2021-01-20' AND DATE '2021-02-09'
    GROUP BY day_of_week, local_hour
),
storm AS (
    SELECT * FROM model_hourly
    WHERE local_date BETWEEN DATE '2021-02-13' AND DATE '2021-02-20'
)
SELECT s.period, s.local_ts, s.local_date, s.local_hour,
       s.demand_mwh, b.base_demand, s.demand_mwh - b.base_demand AS demand_vs_base,
       s.gas_mwh,  b.base_gas,  s.gas_mwh  - b.base_gas  AS gas_vs_base,
       s.wind_mwh, b.base_wind, s.wind_mwh - b.base_wind AS wind_vs_base,
       s.coal_mwh, s.nuclear_mwh, s.solar_mwh, s.total_gen_mwh, b.base_total_gen,
       s.avg_temp_c, b.base_temp, s.avg_temp_c - b.base_temp AS temp_vs_base,
       s.ercot_forecast_mwh,
       -- ERCOT's day-ahead forecast estimates what customers would have used, served demand is what they got
       GREATEST(s.ercot_forecast_mwh - s.demand_mwh, 0) AS forecast_minus_served
FROM storm s
JOIN baseline b USING (day_of_week, local_hour)
ORDER BY s.period;

-- Daily summary for the storm week
CREATE OR REPLACE TABLE uri_daily AS
SELECT local_date,
       ROUND(MIN(avg_temp_c), 1)    AS min_temp_c,
       ROUND(MAX(demand_mwh))       AS peak_demand_mwh,
       ROUND(AVG(demand_mwh))       AS avg_demand_mwh,
       ROUND(AVG(base_demand))      AS avg_base_demand_mwh,
       ROUND(AVG(gas_mwh))          AS avg_gas_mwh,
       ROUND(AVG(base_gas))         AS avg_base_gas_mwh,
       ROUND(AVG(wind_mwh))         AS avg_wind_mwh,
       ROUND(AVG(base_wind))        AS avg_base_wind_mwh,
       ROUND(AVG(nuclear_mwh))      AS avg_nuclear_mwh,
       ROUND(MAX(ercot_forecast_mwh)) AS peak_ercot_forecast_mwh,
       ROUND(SUM(forecast_minus_served)) AS forecast_minus_served_mwh,
       COUNT(*) FILTER (WHERE demand_mwh IS NULL OR total_gen_mwh IS NULL) AS missing_hours
FROM uri_hourly
GROUP BY local_date
ORDER BY local_date;
