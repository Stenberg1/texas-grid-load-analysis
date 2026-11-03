-- Question: when natural gas gets expensive, how much does ERCOT's generation shift from gas to coal?
SET TimeZone = 'UTC';

-- One row per local day: Henry Hub price (ASOF-filled in model_hourly) and the fuel mix.
-- gas_fossil_share = gas / (gas + coal): gas and coal compete for the load left after wind, solar and nuclear.
CREATE OR REPLACE TABLE gas_daily AS
SELECT local_date, year, month, season,
       MAX(henry_hub_usd)                                AS henry_hub_usd,
       SUM(demand_mwh)                                   AS demand_mwh,
       SUM(gas_mwh)                                      AS gas_mwh,
       SUM(coal_mwh)                                     AS coal_mwh,
       SUM(demand_mwh - COALESCE(wind_mwh, 0) - COALESCE(solar_mwh, 0)) AS net_load_mwh,
       100.0 * SUM(gas_mwh)  / SUM(gas_mwh + coal_mwh)   AS gas_fossil_share_pct,
       100.0 * SUM(gas_mwh)  / SUM(total_gen_mwh - COALESCE(storage_mwh, 0)) AS gas_share_pct,
       100.0 * SUM(coal_mwh) / SUM(total_gen_mwh - COALESCE(storage_mwh, 0)) AS coal_share_pct,
       -- Uri week: price spike + forced outages, not economic dispatch
       local_date BETWEEN DATE '2021-02-10' AND DATE '2021-02-20' AS is_uri
FROM model_hourly
WHERE year BETWEEN 2019 AND 2025
GROUP BY local_date, year, month, season
HAVING COUNT(gas_mwh) = COUNT(*);   -- drop days with missing generation

-- Price quintiles WITHIN each year-month, so seasonality, coal retirements and new capacity
-- do not masquerade as a price effect. Uri days excluded. (The controlled regression is in
-- notebooks/04_gas_prices.ipynb.)
CREATE OR REPLACE TABLE gas_price_quintiles AS
WITH ranked AS (
    SELECT *, NTILE(5) OVER (PARTITION BY year, month ORDER BY henry_hub_usd) AS price_quintile
    FROM gas_daily
    WHERE NOT is_uri
)
SELECT price_quintile,
       ROUND(AVG(henry_hub_usd), 2)          AS avg_price_usd,
       ROUND(AVG(gas_fossil_share_pct), 1)   AS gas_fossil_share_pct,
       ROUND(AVG(gas_share_pct), 1)          AS gas_share_pct,
       ROUND(AVG(coal_share_pct), 1)         AS coal_share_pct,
       ROUND(AVG(net_load_mwh) / 24)         AS avg_net_load_mw,
       COUNT(*)                              AS days
FROM ranked
GROUP BY price_quintile
ORDER BY price_quintile;

-- Same view by year: cheapest vs most expensive fifth of days within each month
CREATE OR REPLACE TABLE gas_price_by_year AS
WITH ranked AS (
    SELECT *, NTILE(5) OVER (PARTITION BY year, month ORDER BY henry_hub_usd) AS price_quintile
    FROM gas_daily
    WHERE NOT is_uri
)
SELECT year,
       ROUND(AVG(henry_hub_usd), 2) AS avg_price_usd,
       ROUND(AVG(henry_hub_usd) FILTER (WHERE price_quintile = 1), 2) AS q1_price,
       ROUND(AVG(henry_hub_usd) FILTER (WHERE price_quintile = 5), 2) AS q5_price,
       ROUND(AVG(gas_fossil_share_pct) FILTER (WHERE price_quintile = 1), 1) AS q1_gas_fossil_pct,
       ROUND(AVG(gas_fossil_share_pct) FILTER (WHERE price_quintile = 5), 1) AS q5_gas_fossil_pct,
       ROUND(AVG(gas_fossil_share_pct) FILTER (WHERE price_quintile = 5)
           - AVG(gas_fossil_share_pct) FILTER (WHERE price_quintile = 1), 1) AS shift_pts
FROM ranked
GROUP BY year
ORDER BY year;
