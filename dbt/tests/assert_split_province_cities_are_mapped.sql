-- Every city reported under a split source province (Papua, Papua Barat) must be explicitly
-- assigned to a current province. A new city there cannot be assigned by guessing.
select distinct c.parent_province_name, c.area_name as unassigned_city
from {{ ref('stg_pihps__grid_rows') }} as c
inner join {{ ref('pihps_province_map') }} as m
    on c.parent_province_name = m.source_province_name and m.mapping_type = 'split'
left join {{ ref('pihps_split_cities') }} as s
    on c.parent_province_name = s.source_province_name and c.area_name = s.city_name
where c.area_type = 'city' and s.city_name is null
