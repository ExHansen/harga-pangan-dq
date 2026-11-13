-- The source's province reference list, one row per (snapshot, province).
with cells as (
    select c.snapshot_id, s.fetched_at, c.row_idx, c.field, c.value_text
    from {{ source('parsed', 'raw_cells') }} as c
    inner join {{ ref('stg_pihps__snapshots') }} as s using (snapshot_id)
    where s.endpoint = 'GetRefProvince'
)

select
    snapshot_id,
    fetched_at,
    row_idx,
    try_cast(max(case when field = 'id' then value_text end) as integer) as pihps_province_id,
    trim(max(case when field = 'name' then value_text end)) as province_name
from cells
group by snapshot_id, fetched_at, row_idx
