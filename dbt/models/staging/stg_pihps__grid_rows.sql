-- One row per (snapshot, row) of the commodity grids: who the row is about.
-- A city row does not name its province; it belongs to the nearest province row above it, which is
-- why the loader keeps `row_idx` (row order) from the source.
with grid_cells as (
    select c.snapshot_id, c.row_idx, c.field, c.value_text
    from {{ source('parsed', 'raw_cells') }} as c
    inner join {{ ref('stg_pihps__snapshots') }} as s using (snapshot_id)
    where s.endpoint = 'GetGridDataKomoditas'
),

pivoted as (
    select
        snapshot_id,
        row_idx,
        max(case when field = 'no' then value_text end) as row_no,
        max(case when field = 'name' then value_text end) as area_name_raw,
        max(case when field = 'level' then value_text end) as level_raw
    from grid_cells
    group by snapshot_id, row_idx
),

typed as (
    select
        *,
        trim(area_name_raw) as area_name,
        try_cast(level_raw as integer) as area_level
    from pivoted
),

with_parent as (
    select
        *,
        case area_level when 0 then 'national' when 1 then 'province' when 2 then 'city' end
            as area_type,
        case when area_level = 2 then
            last_value(case when area_level = 1 then area_name end ignore nulls) over (
                partition by snapshot_id order by row_idx
                rows between unbounded preceding and current row
            )
        end as parent_province_name
    from typed
)

select
    snapshot_id,
    row_idx,
    row_no,
    area_name_raw,
    area_name,
    area_level,
    area_type,
    parent_province_name,
    -- stable identity of an area across snapshots
    case area_type
        when 'national' then 'national'
        when 'province' then area_name
        when 'city' then parent_province_name || ' / ' || area_name
    end as area_key
from with_parent
