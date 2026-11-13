-- Daily price per commodity x source province (traditional markets), with changes and the gap
-- to the source's own national figure.
with provinces as (
    select * from {{ ref('int_prices__series') }}
    where area_type = 'province' and price_type_id = 1
),

national as (
    select commodity_id, price_date, price_idr as national_price_idr
    from {{ ref('int_prices__series') }}
    where area_type = 'national' and price_type_id = 1
),

source_provinces as (
    select distinct pihps_province_id, source_province_name
    from {{ ref('pihps_province_map') }}
)

select
    p.price_date,
    p.commodity_id,
    sp.pihps_province_id as source_province_id,
    p.area_name as source_province_name,
    p.price_idr,
    n.national_price_idr,
    100.0 * (p.price_idr / n.national_price_idr - 1) as gap_to_national_pct,
    p.prev_price_date,
    p.prev_price_idr,
    p.days_since_prev,
    p.dod_pct,
    p.week_ago_date,
    p.wow_pct,
    p.log_return,
    p.volatility_20,
    p.is_revised,
    p.snapshot_id
from provinces as p
left join national as n using (commodity_id, price_date)
left join source_provinces as sp on p.area_name = sp.source_province_name
