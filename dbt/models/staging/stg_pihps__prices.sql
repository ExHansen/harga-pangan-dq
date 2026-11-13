-- One row per (snapshot, area, date): every price cell, typed but not judged.
-- `price_raw` keeps the source text ("16,500", "-", or anything unexpected) as evidence for the
-- validity check; `price_idr` is only set when the text is a well-formed rupiah amount.
with snapshots as (
    select *
    from {{ ref('stg_pihps__snapshots') }}
    where endpoint = 'GetGridDataKomoditas'
),

date_cells as (
    select c.snapshot_id, c.row_idx, c.field, c.value_text, c.value_type
    from {{ source('parsed', 'raw_cells') }} as c
    where regexp_full_match(c.field, '[0-9]{2}/[0-9]{2}/[0-9]{4}')
)

select
    s.snapshot_id,
    s.fetched_at,
    s.price_type_id,
    s.comcat_id as commodity_id,
    r.row_idx,
    r.area_type,
    r.area_key,
    r.area_name,
    r.parent_province_name,
    try_strptime(d.field, '%d/%m/%Y')::date as price_date,
    d.field as date_key_raw,
    d.value_text as price_raw,
    d.value_type as price_raw_type,
    coalesce(d.value_text = '-', false) as is_missing,
    case
        when regexp_full_match(d.value_text, '[0-9]{1,3}(,[0-9]{3})*')
            then cast(replace(d.value_text, ',', '') as bigint)
    end as price_idr
from date_cells as d
inner join snapshots as s using (snapshot_id)
inner join {{ ref('stg_pihps__grid_rows') }} as r
    on d.snapshot_id = r.snapshot_id and d.row_idx = r.row_idx
