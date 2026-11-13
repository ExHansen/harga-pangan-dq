-- Commodities: our seed (English names, expected unit) next to what the source's reference list
-- says today, so a renamed item or a changed unit is visible side by side.
with latest_ref as (
    select *
    from {{ ref('stg_pihps__ref_commodities') }}
    where category_id is not null
    qualify row_number() over (partition by item_id order by fetched_at desc) = 1
)

select
    s.commodity_id,
    s.commodity_name,
    s.commodity_name_en,
    s.category_id,
    s.category_name_en,
    s.unit,
    s.unit_note,
    s.plausible_min_idr,
    s.plausible_max_idr,
    r.item_name as source_name,
    r.denomination as source_denomination,
    r.fetched_at as source_checked_at
from {{ ref('commodities') }} as s
left join latest_ref as r on s.commodity_id = r.item_id
