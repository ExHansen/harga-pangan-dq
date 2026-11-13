# harga-pangan-dq

A live data-quality monitor for Indonesian strategic food prices. Every business day it collects
province-level prices from PIHPS Nasional (Bank Indonesia), models them with dbt, runs
data-quality checks that record incidents, and publishes a dashboard that shows both the prices
and the health of the data.

> **Status: M2 of 7. Not live yet.**
> - Ingestion covers all 21 commodities in every province and sample city. The raw store is
>   immutable and append-only.
> - A dbt project (DuckDB) models staging → intermediate → marts, with enforced contracts on every
>   mart and an explicit 34 → 38 province mapping.
> - CI runs lint, type-check, unit tests, dbt build and tests on recorded fixtures, and a Docker
>   build.
> - The headline reliability numbers will be generated from real run history after 30 days of
>   running (M7). None are shown before then.

## Try it

```bash
uv sync
uv run hpdq ingest --dry-run                                  # print today's 23-request plan, no network
uv run hpdq ingest --date 2026-11-12                          # fetch D-7..D for all 21 commodities into ./data
uv run hpdq ingest --date 2026-11-12                          # again: nothing new is stored (idempotent)
uv run hpdq backfill --start 2026-08-01 --end 2026-11-11      # history, one month per request, resumable
uv run hpdq raw verify                                        # every stored file matches its hash and metadata
uv run hpdq build                                             # raw -> Parquet -> dbt build (seeds, models, tests)
uv run hpdq docs                                              # regenerate docs/data-dictionary.md
```

Everything under `./build` (warehouse, dbt artifacts) is disposable: `rm -rf build && hpdq build`
rebuilds it from raw in about 11 seconds.

## Data source and licence

Prices come from **Pusat Informasi Harga Pangan Strategis (PIHPS) Nasional, Bank Indonesia**,
<https://www.bi.go.id/hargapangan>.

- The source publishes no open licence ("Hak Cipta © PIHPS Nasional - Semua Hak Dilindungi").
- This is a non-commercial research and portfolio project. It cites the source in full (UU 28/2014
  Pasal 44(1)(a)) and is **not an official statistic**.
- Access is polite and once per day:
  - one request every ≥3 s;
  - it stops on HTTP 403/429;
  - it identifies itself as `harga-pangan-dq/<version> (+https://github.com/ExHansen/harga-pangan-dq)`.
- Details: [docs/phase0-source-discovery.md](docs/phase0-source-discovery.md).

## Docs

- [Design and decision records](docs/design.md)
- [Data dictionary](docs/data-dictionary.md) (generated from the dbt project)
- [Milestone plan](docs/plan.md)

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Tests never touch the network: a guard in `tests/conftest.py` fails any socket connection. The
dbt project is built and tested on recorded fixtures inside the test suite.

## License

Code: MIT. Data: see *Data source and licence* above.
