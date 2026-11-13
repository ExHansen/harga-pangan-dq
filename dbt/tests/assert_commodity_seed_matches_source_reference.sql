-- The commodity ids in our seed must equal the source's latest reference list, both ways.
with latest_ref as (
    select item_id as commodity_id
    from {{ ref('stg_pihps__ref_commodities') }}
    where category_id is not null
    qualify fetched_at = max(fetched_at) over ()
)

(select 'missing_in_seed' as problem, commodity_id from latest_ref
 except select 'missing_in_seed', commodity_id from {{ ref('commodities') }})
union all
(select 'missing_in_source' as problem, commodity_id from {{ ref('commodities') }}
 except select 'missing_in_source', commodity_id from latest_ref)
