-- The source's commodity reference list, one row per (snapshot, item). Categories have cat_id null.
with cells as (
    select c.snapshot_id, s.fetched_at, c.row_idx, c.field, c.value_text
    from {{ source('parsed', 'raw_cells') }} as c
    inner join {{ ref('stg_pihps__snapshots') }} as s using (snapshot_id)
    where s.endpoint = 'GetRefCommodityAndCategory'
)

select
    snapshot_id,
    fetched_at,
    row_idx,
    max(case when field = 'id' then value_text end) as item_id,
    trim(max(case when field = 'name' then value_text end)) as item_name,
    max(case when field = 'cat_id' then value_text end) as category_id,
    max(case when field = 'denomination' then value_text end) as denomination,
    try_cast(max(case when field = 'sort' then value_text end) as integer) as sort_order
from cells
group by snapshot_id, fetched_at, row_idx
