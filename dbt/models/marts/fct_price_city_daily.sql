-- Daily price per commodity x sample city, each city assigned to its *current* (38-province)
-- province: one-to-one provinces map directly; cities in the provinces split in 2022 use the
-- explicit city list (pihps_split_cities). This is what makes a 38-province view possible.
with cities as (
    select * from {{ ref('int_prices__series') }}
    where area_type = 'city' and price_type_id = 1
),

one_to_one as (
    select source_province_name, iso_code
    from {{ ref('pihps_province_map') }}
    where mapping_type = 'one_to_one'
)

select
    c.price_date,
    c.commodity_id,
    c.parent_province_name as source_province_name,
    c.area_name as city_name,
    coalesce(o.iso_code, s.iso_code) as province_iso_code,
    c.price_idr,
    c.prev_price_date,
    c.days_since_prev,
    c.dod_pct,
    c.wow_pct,
    c.is_revised,
    c.snapshot_id
from cities as c
left join one_to_one as o on c.parent_province_name = o.source_province_name
left join {{ ref('pihps_split_cities') }} as s
    on c.parent_province_name = s.source_province_name and c.area_name = s.city_name
