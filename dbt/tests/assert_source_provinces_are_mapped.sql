-- Every province name the source publishes must be in the explicit 34 -> 38 map.
-- A new or renamed source province fails the build instead of disappearing from the marts.
select distinct p.area_name as unmapped_source_province
from {{ ref('stg_pihps__grid_rows') }} as p
left join {{ ref('pihps_province_map') }} as m on p.area_name = m.source_province_name
where p.area_type = 'province' and m.source_province_name is null
