-- How volatile each commodity is per province (and nationally), over the last 60 observations of
-- each series. Volatility = sample standard deviation of daily log returns.
with series as (
    select
        *,
        row_number() over (
            partition by commodity_id, area_key order by price_date desc
        ) as recency
    from {{ ref('int_prices__series') }}
    where area_type in ('national', 'province') and price_type_id = 1
)

select
    commodity_id,
    area_type,
    area_name,
    max(price_date) as as_of_date,
    min(price_date) as window_start_date,
    count(log_return) as n_returns,
    stddev_samp(log_return) as volatility_60,
    avg(abs(dod_pct)) as mean_abs_dod_pct,
    max(abs(dod_pct)) as max_abs_dod_pct
from series
where recency <= 60
group by commodity_id, area_type, area_name
