-- The 34 provinces PIHPS reports (pre-2022 boundaries) and the current provinces each one covers.
-- "Papua" in the source covers 4 provinces today and "Papua Barat" covers 2: a source-province
-- price for them is an average over cities that now sit in different provinces.
select
    m.pihps_province_id as source_province_id,
    m.source_province_name,
    min(m.mapping_type) as mapping_type,
    count(*) as current_province_count,
    string_agg(p.province_name, ', ' order by p.province_name) as current_provinces,
    string_agg(m.iso_code, ', ' order by m.iso_code) as current_iso_codes,
    min(p.island_group) as island_group
from {{ ref('pihps_province_map') }} as m
inner join {{ ref('provinces') }} as p using (iso_code)
group by m.pihps_province_id, m.source_province_name
