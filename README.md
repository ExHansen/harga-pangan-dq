# harga-pangan-dq

A live data-quality monitor for Indonesian strategic food prices. Every business day it collects
province-level prices from PIHPS Nasional (Bank Indonesia), models them with dbt, runs
data-quality checks that record incidents, and publishes a dashboard that shows both the prices
and the health of the data.

> **Status: M1 of 7. Not live yet.**
> Ingestion runs for one commodity group (chillies). The raw store is immutable and append-only.
> Parser tests run on recorded fixtures. CI runs lint, type-check and tests.
> The headline reliability numbers will be generated from real run history after 30 days of
> running (M7). None are shown before then.

## Try it

```bash
uv sync
uv run hpdq ingest --dry-run              # print the request plan, no network
uv run hpdq ingest --date 2026-11-11      # fetch D-7..D for the chillies group into ./data
uv run hpdq ingest --date 2026-11-11      # run again: nothing new is stored (idempotent)
uv run hpdq raw verify                    # prove every stored file matches its hash and metadata
uv run hpdq load                          # raw -> lossless long Parquet in ./build/parsed
```

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
- [Milestone plan](docs/plan.md)

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Tests never touch the network: a guard in `tests/conftest.py` fails any socket connection.

## License

Code: MIT. Data: see *Data source and licence* above.
