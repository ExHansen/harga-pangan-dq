# Milestone plan

MVP = M1–M4. The 30-day clock starts at the first successful **scheduled** run after M4.

Every milestone ends with:

- test output showing everything passes;
- what changed and what is left;
- an "explain it to me" section: 5 bullets and 3 interview questions with answers.

I never push. You push `main`, and the bot pushes the `data` branch once it is live.

## M1 — Skeleton, CI, and ingestion for one commodity group

Commodity group: **chillies**, 4 items:

- *cabai merah besar*, *cabai merah keriting*
- *cabai rawit hijau*, *cabai rawit merah*

Chillies are the most volatile group, so they exercise the anomaly logic early.

- The uv project on Python 3.12, `hpdq` Typer CLI, ruff, mypy, pytest, Dockerfile, local `git init`
  with no remote.
- PIHPS client: User-Agent, ≥3 s rate limit, retry/backoff, stop on 403/429, request cap.
- Raw store: deterministic gzip, SHA-256 names, append-only guard, manifest.
- Lossless parser → long Parquet. Fixtures recorded from real responses. The test suite blocks
  network access.
- Verify `showKota=true` (1–2 requests) and fix ADR-006.
- `ci.yml`: ruff, mypy, pytest, docker build.

**Done when:**

- `hpdq ingest --date <D>` writes raw;
- a second run writes **nothing**;
- the parser tests pass on fixtures;
- CI is green locally (`act` is not required; the same commands run via `uv run`).

## M2 — dbt models, tests, province mapping

- Enable all 21 commodities (a config change).
- Bootstrap backfill of the last ~12 months, about 21–42 requests, so baselines exist.
- Seeds: 38 provinces, the 34→38 map, commodities with expected unit and plausible range.
- Staging, intermediate and marts. Contracts on marts. Custom generic tests.
- `docs/data-dictionary.md`.

**Done when:** `dbt build` is green on fixtures and on local data, and the contracts are enforced.

## M3 — Checks, incidents table, GitHub Issues

- Checks 1–7 with business reason, rule and severity.
- Quarantine table, incident event log, auto-resolve.
- Seeds for `calendar_holidays` (2026–2027 from the SKB decree) and `seasonal_windows` (2018–2027).
- GitHub Issue open, comment and close via REST, tested with `MockTransport`.
- `incident-sync.yml`: closing an issue or adding the `false-alarm` label is recorded.
- `docs/checks.md`, including how the anomaly classification works with worked examples.

**Done when:**

- every check has synthetic-data tests for pass, fail and edge cases (MAD = 0, gaps, seasonal
  windows);
- a run on real recent data shows sensible output, reviewed together.

## M4 — Dashboard deployed and daily schedule live

- Evidence site with Latest prices, Commodity trends, Data health, Incidents, About. Citation and
  disclaimer on every page; mobile check.
- `daily.yml`: two crons plus dispatch, `data` branch, append-only assertion, Pages deploy.
- `backfill.yml` (dispatch).

**Your steps:**

1. Create the GitHub repo.
2. Push `main` and `data`.
3. Set Actions → workflow permissions to read/write.
4. Set Pages → source "GitHub Actions".

**Done when:** a scheduled run succeeds end to end and the site is live. **The clock starts here.**

## M5 — Fault injection with generated results

- 6 faults plus a clean baseline in an isolated workspace.
- Results are written to `docs/results/fault-injection.md` and the README markers.
- Runs offline in CI on every push.

**Done when:** the clean run gives 0 incidents, every fault is detected or honestly reported as
missed, and nothing is typed by hand.

## M6 — Full backfill and the analysis write-up

- Backfill 2018 → today via `backfill.yml`, about 190 requests spread out.
- Calibrate anomaly thresholds on history, and report how Lebaran-window flags were classified.
- `docs/analysis.md` answers 2 questions:
  1. Which commodity × province pairs are the most volatile, and is volatility structural
     (island/eastern regions)?
  2. How do prices move around Idul Fitri (an event study from t−30 to t+14 days, 2018–2026)?
- Charts come from scripts and every number from queries in the repo.

**Done when:** re-running `hpdq analysis` regenerates every number and chart.

## M7 — Reliability report, README polish, demo script

- `hpdq report` → README "Live results" + `docs/results/reliability.md` after 30 days.
- README:
  - first paragraph with the live link and headline numbers;
  - Mermaid diagram, data sources and licence, design decisions, limitations.
- A 60-second demo script.

**Done when:** every number in the README is generated, and the README has been reviewed by you.
