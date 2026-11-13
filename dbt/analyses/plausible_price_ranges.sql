-- Suggested plausible price range per commodity, for the validity check (M3).
-- The result is copied into seeds/commodities.csv (plausible_min_idr, plausible_max_idr); the seed
-- description records which data window it was computed on.
--
-- Rule: [p0.5 / 3, p99.5 x 3] over every observed province and city price, rounded *outward* to
-- two significant digits. Deliberately wide: this range only has to reject impossible values
-- (a x1000 typo, a zero). Subtler errors (a price per ons instead of per kg) are the job of the
-- unit and anomaly checks, which compare with the series' own history.
--
-- Run: dbt compile --select plausible_price_ranges, then execute the compiled SQL in the warehouse.
with prices as (
    select commodity_id, price_idr from {{ ref('fct_price_city_daily') }}
    union all
    select commodity_id, price_idr from {{ ref('fct_price_daily') }}
),

stats as (
    select
        commodity_id,
        count(*) as n_prices,
        min(price_idr) as observed_min_idr,
        max(price_idr) as observed_max_idr,
        quantile_cont(price_idr, 0.005) as p005,
        quantile_cont(price_idr, 0.995) as p995
    from prices
    group by commodity_id
),

bounds as (
    select *, p005 / 3 as raw_min, p995 * 3 as raw_max
    from stats
)

select
    commodity_id,
    n_prices,
    observed_min_idr,
    observed_max_idr,
    cast(
        floor(raw_min / pow(10, floor(log10(raw_min)) - 1)) * pow(10, floor(log10(raw_min)) - 1)
        as bigint
    ) as plausible_min_idr,
    cast(
        ceil(raw_max / pow(10, floor(log10(raw_max)) - 1)) * pow(10, floor(log10(raw_max)) - 1)
        as bigint
    ) as plausible_max_idr
from bounds
order by cast(substr(commodity_id, 5) as integer)
