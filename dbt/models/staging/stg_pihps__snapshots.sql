-- One row per raw snapshot: request parameters unpacked from the sidecar metadata.
select
    snapshot_id,
    endpoint,
    request_key,
    json_extract_string(params_json, '$.comcat_id') as comcat_id,
    try_cast(json_extract_string(params_json, '$.price_type_id') as integer) as price_type_id,
    json_extract_string(params_json, '$.showKota') = 'true' as includes_cities,
    try_cast(json_extract_string(params_json, '$.start_date') as date) as window_start,
    try_cast(json_extract_string(params_json, '$.end_date') as date) as window_end,
    fetched_at,
    sha256,
    bytes as body_bytes,
    run_id,
    status as parse_status,
    error as parse_error,
    top_level_keys,
    row_count,
    row_keys,
    date_key_count,
    levels,
    value_types
from {{ source('parsed', 'snapshots') }}
