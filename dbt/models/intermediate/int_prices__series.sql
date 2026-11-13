-- Observed prices as time series, one series per (price type, commodity, area), with changes.
--
-- * Day-over-day compares with the previous *observation* of the same series, which skips
--   weekends and holidays (PIHPS publishes on business days); `days_since_prev` keeps the gap
--   visible, e.g. 3 after a weekend, ~10 across the Lebaran break.
-- * Week-over-week compares with the latest observation on or before D-7, and only if that
--   observation is at most 14 days old (otherwise the comparison would silently span months).
-- * volatility_20 is the sample standard deviation of the last 20 log returns (null until 20).
with observed as (
    select
        price_type_id,
        commodity_id,
        area_type,
        area_key,
        area_name,
        parent_province_name,
        price_date,
        price_idr,
        is_revised,
        snapshot_id
    from {{ ref('int_prices__current') }}
    where price_idr is not null
),

lagged as (
    select
        *,
        lag(price_date) over series as prev_price_date,
        lag(price_idr) over series as prev_price_idr
    from observed
    window series as (
        partition by price_type_id, commodity_id, area_key order by price_date
    )
),

with_returns as (
    select
        *,
        date_diff('day', prev_price_date, price_date) as days_since_prev,
        100.0 * (price_idr / prev_price_idr - 1) as dod_pct,
        ln(price_idr / prev_price_idr) as log_return,
        price_date - 7 as week_ago_target
    from lagged
),

with_week_ago as (
    select
        r.*,
        w.price_date as week_ago_date,
        w.price_idr as week_ago_price_idr
    from with_returns as r
    asof left join observed as w
        on r.price_type_id = w.price_type_id
        and r.commodity_id = w.commodity_id
        and r.area_key = w.area_key
        and r.week_ago_target >= w.price_date
)

select
    price_type_id,
    commodity_id,
    area_type,
    area_key,
    area_name,
    parent_province_name,
    price_date,
    price_idr,
    prev_price_date,
    prev_price_idr,
    days_since_prev,
    dod_pct,
    log_return,
    case when date_diff('day', week_ago_date, price_date) <= 14 then week_ago_date end
        as week_ago_date,
    case
        when date_diff('day', week_ago_date, price_date) <= 14
            then 100.0 * (price_idr / week_ago_price_idr - 1)
    end as wow_pct,
    case
        when count(log_return) over last_20 = 20 then stddev_samp(log_return) over last_20
    end as volatility_20,
    is_revised,
    snapshot_id
from with_week_ago
window last_20 as (
    partition by price_type_id, commodity_id, area_key
    order by price_date
    rows between 19 preceding and current row
)
