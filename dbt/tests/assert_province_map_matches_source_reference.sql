-- The (id, name) pairs in our map must equal the source's latest GetRefProvince list, both ways.
with latest_ref as (
    select pihps_province_id, province_name
    from {{ ref('stg_pihps__ref_provinces') }}
    qualify fetched_at = max(fetched_at) over ()
),

seed as (
    select distinct pihps_province_id, source_province_name as province_name
    from {{ ref('pihps_province_map') }}
)

(select 'missing_in_seed' as problem, * from latest_ref except select 'missing_in_seed', * from seed)
union all
(select 'missing_in_source' as problem, * from seed except select 'missing_in_source', * from latest_ref)
