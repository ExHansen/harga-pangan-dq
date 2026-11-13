-- The source's national figure ("Semua Provinsi") per commodity and day, with changes and how
-- many provinces reported that day.
with national as (
    select * from {{ ref('int_prices__series') }}
    where area_type = 'national' and price_type_id = 1
),

reporting as (
    select commodity_id, price_date, count(*) as provinces_reporting
    from {{ ref('int_prices__series') }}
    where area_type = 'province' and price_type_id = 1
    group by all
)

select
    n.price_date,
    n.commodity_id,
    n.price_idr,
    n.prev_price_date,
    n.days_since_prev,
    n.dod_pct,
    n.week_ago_date,
    n.wow_pct,
    n.volatility_20,
    coalesce(r.provinces_reporting, 0) as provinces_reporting,
    n.is_revised,
    n.snapshot_id
from national as n
left join reporting as r using (commodity_id, price_date)
