-- The source's *current* word on every price cell.
--
-- Overlapping windows mean a (commodity, date) can appear in many snapshots: the daily D-7..D
-- windows, monthly backfill windows, and same-day re-fetches. For each (price type, commodity, date)
-- the authoritative snapshot is the most recently fetched one that contains that date, and *all*
-- areas for that date come from it. So a later publication that fills a late province, revises a
-- value, or blanks one, wins as a whole. Values are never mixed across snapshots for one date.
with prices as (
    select * from {{ ref('stg_pihps__prices') }}
),

snapshot_dates as (
    select distinct price_type_id, commodity_id, price_date, snapshot_id, fetched_at
    from prices
),

chosen as (
    select price_type_id, commodity_id, price_date, snapshot_id
    from snapshot_dates
    qualify row_number() over (
        partition by price_type_id, commodity_id, price_date
        order by fetched_at desc, snapshot_id desc
    ) = 1
),

history as (
    select
        price_type_id,
        commodity_id,
        price_date,
        area_key,
        count(distinct snapshot_id) as n_snapshots,
        count(distinct coalesce(price_raw, '<null>')) as n_distinct_values
    from prices
    group by all
)

select
    p.price_type_id,
    p.commodity_id,
    p.price_date,
    p.area_type,
    p.area_key,
    p.area_name,
    p.parent_province_name,
    p.price_raw,
    p.price_idr,
    p.is_missing,
    h.n_snapshots,
    h.n_distinct_values > 1 as is_revised,
    p.snapshot_id,
    p.fetched_at,
    p.row_idx
from prices as p
inner join chosen as c using (price_type_id, commodity_id, price_date, snapshot_id)
inner join history as h using (price_type_id, commodity_id, price_date, area_key)
