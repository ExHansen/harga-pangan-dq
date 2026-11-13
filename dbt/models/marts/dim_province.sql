-- Indonesia's 38 provinces (ISO 3166-2:ID), and which source province reports for each.
with source_map as (
    select
        iso_code,
        min(source_province_name) as source_province_name,
        min(pihps_province_id) as source_province_id,
        min(mapping_type) as mapping_type
    from {{ ref('pihps_province_map') }}
    group by iso_code
)

select
    p.iso_code,
    p.province_name,
    p.province_name_en,
    p.island_group,
    p.split_from_iso_code,
    p.legal_basis,
    m.source_province_id,
    m.source_province_name,
    m.mapping_type
from {{ ref('provinces') }} as p
left join source_map as m using (iso_code)
