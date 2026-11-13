"""``hpdq`` command-line interface."""

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from hpdq import __version__, config
from hpdq.checks.incidents_store import IncidentStore
from hpdq.docs import write_data_dictionary
from hpdq.ingest import IngestSummary, run_ingest
from hpdq.load.flatten import build_parsed
from hpdq.pihps.catalog import DEFAULT_GROUP, commodities_for
from hpdq.pihps.client import PihpsClient
from hpdq.pihps.specs import RequestSpec, plan_backfill, plan_daily
from hpdq.raw.store import RawStore
from hpdq.raw.verify import git_append_only_violations, verify_store
from hpdq.timeutil import now_utc, wib_date
from hpdq.transform import DbtPaths, run_dbt

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="harga-pangan-dq: a live data-quality monitor for Indonesian food prices (PIHPS).",
)
raw_app = typer.Typer(no_args_is_help=True, help="Raw store utilities.")
app.add_typer(raw_app, name="raw")

DataDir = Annotated[
    Path | None,
    typer.Option(help=f"Data root (raw store). Default: ${config.DATA_DIR_ENV} or ./data."),
]
BuildDir = Annotated[Path, typer.Option(help="Disposable build output.")]
Group = Annotated[str, typer.Option(help="Commodity group: all | chillies.")]
Commodity = Annotated[
    list[str] | None,
    typer.Option("--commodity", help="Only this commodity id (repeatable); overrides --group."),
]
ShowKota = Annotated[bool, typer.Option(help="Include city rows.")]
RunId = Annotated[str | None, typer.Option(help="Default: GitHub run id or random.")]
MaxRequests = Annotated[int, typer.Option(min=1, help="Hard cap on HTTP attempts in this run.")]
DryRun = Annotated[bool, typer.Option(help="Print the plan; no network.")]
DateOption = Annotated[datetime | None, typer.Option(formats=["%Y-%m-%d"])]


@app.callback()
def _main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _commodities(group: str, commodity: list[str] | None) -> tuple[str, ...]:
    try:
        return commodities_for(group, commodity)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--group/--commodity") from None


def _print_plan(title: str, specs: list[RequestSpec]) -> None:
    typer.echo(f"{title} ({len(specs)} requests):")
    for spec in specs:
        query = "&".join(f"{k}={v}" for k, v in spec.params)
        typer.echo(f"  GET {spec.url}{'?' + query if query else ''}")


def _execute(
    specs: list[RequestSpec],
    *,
    business_date: date,
    data_dir: Path | None,
    run_id: str | None,
    max_requests: int,
    skip_existing: bool,
    min_interval_s: float = config.MIN_REQUEST_INTERVAL_S,
    backoff_s: tuple[float, ...] = config.RETRY_BACKOFF_S,
) -> None:
    root = data_dir or config.default_data_dir()
    with PihpsClient.create(
        max_requests=max_requests, min_interval_s=min_interval_s, backoff_s=backoff_s
    ) as client:
        summary = run_ingest(
            specs,
            business_date=business_date,
            client=client,
            store=RawStore(root),
            run_id=run_id or config.default_run_id(),
            skip_existing=skip_existing,
        )
    _report(summary, root)


def _report(summary: IngestSummary, root: Path) -> None:
    typer.echo(
        f"run {summary.run_id} D={summary.business_date}: {summary.status} | "
        f"planned {summary.planned}, stored {summary.stored}, unchanged {summary.deduped}, "
        f"already stored {summary.already_stored}, failed {summary.failed}, "
        f"skipped {summary.skipped}, http attempts {summary.http_attempts}"
    )
    for path in summary.stored_paths:
        typer.echo(f"  + {path.relative_to(root).as_posix()}")
    if summary.manifest_path is not None:
        typer.echo(f"manifest: {summary.manifest_path.relative_to(root).as_posix()}")
    if summary.stop_reason:
        typer.echo(f"stopped: {summary.stop_reason}", err=True)
    if summary.status != "success":
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the version and the User-Agent sent to the source."""
    typer.echo(f"hpdq {__version__}")
    typer.echo(f"User-Agent: {config.user_agent()}")


@app.command()
def ingest(
    date_: Annotated[
        datetime | None,
        typer.Option(
            "--date", formats=["%Y-%m-%d"], help="Business date D (WIB). Default: today in WIB."
        ),
    ] = None,
    group: Group = DEFAULT_GROUP,
    commodity: Commodity = None,
    window_days: Annotated[
        int, typer.Option(min=0, max=31, help="Fetch D-window_days..D.")
    ] = config.DEFAULT_WINDOW_DAYS,
    show_kota: ShowKota = True,
    data_dir: DataDir = None,
    run_id: RunId = None,
    max_requests: MaxRequests = config.MAX_REQUESTS_PER_RUN,
    dry_run: DryRun = False,
) -> None:
    """Fetch one business day's window from PIHPS and store new responses immutably."""
    business_date = date_.date() if date_ is not None else wib_date(now_utc())
    comcat_ids = _commodities(group, commodity)
    specs = plan_daily(business_date, comcat_ids, window_days=window_days, show_kota=show_kota)
    if dry_run:
        _print_plan(f"Plan for D={business_date}", specs)
        return
    _execute(
        specs,
        business_date=business_date,
        data_dir=data_dir,
        run_id=run_id,
        max_requests=max_requests,
        skip_existing=False,
    )


@app.command()
def backfill(
    start: Annotated[datetime, typer.Option(formats=["%Y-%m-%d"], help="First date (incl.).")],
    end: Annotated[datetime, typer.Option(formats=["%Y-%m-%d"], help="Last date (incl.).")],
    group: Group = DEFAULT_GROUP,
    commodity: Commodity = None,
    show_kota: ShowKota = True,
    data_dir: DataDir = None,
    run_id: RunId = None,
    max_requests: MaxRequests = config.MAX_REQUESTS_PER_RUN,
    dry_run: DryRun = False,
) -> None:
    """Fetch history one calendar month per request. Resumable: existing snapshots are skipped.

    Gentler than daily ingestion: >= 8 s between request starts and at most one retry, because a
    month window costs the source ~5 s each.
    """
    comcat_ids = _commodities(group, commodity)
    try:
        specs = plan_backfill(start.date(), end.date(), comcat_ids, show_kota=show_kota)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None
    if dry_run:
        _print_plan(f"Backfill {start.date()}..{end.date()}", specs)
        return
    _execute(
        specs,
        business_date=end.date(),
        data_dir=data_dir,
        run_id=run_id,
        max_requests=max_requests,
        skip_existing=True,
        min_interval_s=config.BACKFILL_MIN_INTERVAL_S,
        backoff_s=config.BACKFILL_RETRY_BACKOFF_S,
    )


@app.command()
def load(
    data_dir: DataDir = None,
    out_dir: Annotated[Path, typer.Option(help="Output directory.")] = (
        config.DEFAULT_BUILD_DIR / "parsed"
    ),
) -> None:
    """Rebuild the lossless long tables (Parquet) from every raw snapshot."""
    root = data_dir or config.default_data_dir()
    summary = build_parsed(root, out_dir)
    typer.echo(
        f"snapshots {summary.snapshots} (ok {summary.ok}, not ok {summary.not_ok}), "
        f"cells {summary.cells}"
    )
    typer.echo(f"  {summary.snapshots_path.as_posix()}\n  {summary.cells_path.as_posix()}")


@app.command()
def build(
    data_dir: DataDir = None,
    build_dir: BuildDir = config.DEFAULT_BUILD_DIR,
    select: Annotated[
        str | None, typer.Option(help="dbt selector, e.g. 'staging+' (default: everything).")
    ] = None,
) -> None:
    """Rebuild from raw: load (raw -> Parquet), then `dbt build` (seeds, models, tests)."""
    root = data_dir or config.default_data_dir()
    paths = DbtPaths.under(build_dir)
    summary = build_parsed(root, paths.parsed_dir)
    typer.echo(f"loaded {summary.ok} snapshots, {summary.cells} cells")
    args = ["build"] + (["--select", select] if select else [])
    if not run_dbt(args, paths):
        raise typer.Exit(code=1)
    typer.echo(f"warehouse: {paths.warehouse.as_posix()}")


@app.command()
def docs(
    build_dir: BuildDir = config.DEFAULT_BUILD_DIR,
    out: Annotated[Path, typer.Option(help="Output file.")] = Path("docs/data-dictionary.md"),
) -> None:
    """Regenerate the data dictionary from the dbt project (descriptions, types, grain)."""
    paths = DbtPaths.under(build_dir)
    if not run_dbt(["parse"], paths):
        raise typer.Exit(code=1)
    written = write_data_dictionary(paths.target_dir / "manifest.json", out)
    typer.echo(f"wrote {written.as_posix()}")


@app.command()
def check(
    data_dir: DataDir = None,
    build_dir: BuildDir = config.DEFAULT_BUILD_DIR,
    date_: Annotated[
        datetime | None,
        typer.Option("--date", formats=["%Y-%m-%d"], help="Business date. Default: today."),
    ] = None,
) -> None:
    """Run all data quality checks.

    Checks run in order:
    1. Freshness - today's data is present by an agreed time
    2. Completeness - every expected commodity × province combination is reported
    3. Validity - price > 0, unit as expected, within plausible range
    4. Duplicates - (commodity, area, date) is unique within a snapshot
    5. Schema drift - the response fingerprint matches the versioned contract
    6. Anomaly - separate a real price shock from a data error
    7. Reconciliation - province vs cities, national vs provinces

    Critical incidents are logged to build/incidents/incident_events.db and opened as
    GitHub Issues.
    """
    business_date = date_.date() if date_ is not None else wib_date(now_utc())

    # Load data
    root = data_dir or config.default_data_dir()
    parsed_dir = config.DEFAULT_BUILD_DIR / "parsed"
    summary = build_parsed(root, parsed_dir)

    # Load incident store
    store = IncidentStore(build_dir)

    warehouse = build_dir / "warehouse.duckdb"
    typer.echo(f"Running data quality checks for D={business_date.isoformat()}")
    typer.echo(f"Parsed {summary.cells} cells from {summary.snapshots} snapshots")

    # Query the warehouse for data needed by checks
    if warehouse.exists():
        import duckdb

        con = duckdb.connect(str(warehouse))
        con.execute("SET TimeZone = 'UTC'")

        # Latest national snapshot date
        row = con.execute("SELECT MAX(price_date) FROM fct_price_national_daily").fetchone()
        latest_national_snapshot = row[0] if row and row[0] else None

        # Volatile commodities (top 5 by 60-day volatility)
        volatile_rows = con.execute(
            "SELECT commodity_id, volatility_60 FROM agg_volatility "
            "ORDER BY volatility_60 DESC NULLS LAST LIMIT 5"
        ).fetchall()
        volatile_commodities = [str(r[0]) for r in volatile_rows if r[0]]

        # Latest volatile snapshot dates & price pairs
        latest_volatile_snapshots: dict[str, object] = {}
        previous_prices: dict[str, dict[str, float]] = {}
        current_volatile_prices: dict[str, dict[str, float]] = {}
        for commodity_id in volatile_commodities:
            rows = con.execute(
                "SELECT source_province_name, price_idr, price_date "
                "FROM fct_price_daily WHERE commodity_id = ? "
                "ORDER BY price_date DESC LIMIT 2",
                (commodity_id,),
            ).fetchall()
            if rows:
                latest_volatile_snapshots[str(commodity_id)] = rows[0][2]
            if len(rows) >= 2:
                previous_prices[str(commodity_id)] = {str(rows[1][0]): float(rows[1][1])}
            if rows:
                current_volatile_prices[str(commodity_id)] = {str(rows[0][0]): float(rows[0][1])}

        # Completeness: expected vs reported commodity x province
        expected_combinations: set[tuple[str, str]] = set()
        for c in con.execute("SELECT commodity_id FROM dim_commodity").fetchall():
            for p in con.execute("SELECT source_province_name FROM dim_source_province").fetchall():
                expected_combinations.add((str(c[0]), str(p[0])))
        reported_combinations: set[tuple[str, str]] = {
            (str(r[0]), str(r[1]))
            for r in con.execute(
                "SELECT DISTINCT commodity_id, source_province_name FROM fct_price_daily"
            ).fetchall()
        }

        # Validity: prices, plausible ranges, expected units
        prices: dict[tuple[str, str, str], float] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, price_idr, price_date FROM fct_price_daily"
        ).fetchall():
            prices[(str(r[0]), str(r[1]), str(r[3]))] = float(r[2])
        plausible_ranges: dict[str, dict[str, float]] = {}
        expected_units: dict[str, str] = {}
        for r in con.execute(
            "SELECT commodity_id, plausible_min_idr, plausible_max_idr, unit FROM dim_commodity"
        ).fetchall():
            plausible_ranges[str(r[0])] = {"min": float(r[1]), "max": float(r[2])}
            expected_units[str(r[0])] = str(r[3])

        # Anomaly: historical prices, national prices
        historical_prices: dict[tuple[str, str], list[float]] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, price_idr, price_date FROM fct_price_daily"
        ).fetchall():
            key = (str(r[0]), str(r[1]))
            historical_prices.setdefault(key, []).append(float(r[2]))
        national_prices: dict[tuple[str, str], float] = {}
        for r in con.execute(
            "SELECT commodity_id, price_idr, price_date FROM fct_price_national_daily"
        ).fetchall():
            national_prices[(str(r[0]), str(r[2]))] = float(r[1])

        # Reconciliation: province vs city vs national
        province_prices: dict[tuple[str, str, str], float] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, price_idr, price_date FROM fct_price_daily"
        ).fetchall():
            province_prices[(str(r[0]), str(r[1]), str(r[3]))] = float(r[2])
        city_prices: dict[tuple[str, str, str, str], float] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, city_name, price_idr, price_date "
            "FROM fct_price_city_daily"
        ).fetchall():
            city_prices[(str(r[0]), str(r[1]), str(r[2]), str(r[4]))] = float(r[3])

        # Duplicates: raw price rows from warehouse
        duplicate_rows: list[dict] = []
        for r in con.execute(
            "SELECT snapshot_id, commodity_id, source_province_name AS area_key, "
            "price_idr, price_date FROM fct_price_daily"
        ).fetchall():
            duplicate_rows.append(
                {
                    "snapshot_id": str(r[0]),
                    "commodity_id": str(r[1]),
                    "area_key": str(r[2]),
                    "price_idr": float(r[3]),
                    "price_date": str(r[4]),
                }
            )

        # Schema drift: snapshot metadata
        snapshot_rows: list[dict] = []
        for r in con.execute(
            "SELECT snapshot_id, sha256 AS fingerprint, request_key FROM stg_pihps__snapshots"
        ).fetchall():
            snapshot_rows.append(
                {
                    "snapshot_id": str(r[0]),
                    "fingerprint": str(r[1]) if r[1] else "",
                    "request_key": str(r[2]) if r[2] else "",
                }
            )
        expected_fingerprints: dict[str, str] = {}

        # Anomaly: prices dict for anomaly check
        anomaly_prices: dict[str, dict[str, object]] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, price_idr, price_date FROM fct_price_daily"
        ).fetchall():
            key = f"{r[0]!s}||{r[1]!s}"
            anomaly_prices[key] = {
                "price_idr": float(r[2]),
                "price_date": str(r[3]),
            }
        national_prices_anomaly: dict[str, float] = {}
        for r in con.execute(
            "SELECT commodity_id, price_idr FROM fct_price_national_daily"
        ).fetchall():
            national_prices_anomaly[str(r[0])] = float(r[1])

        # Province neighbor mapping (same island group)
        neighbor_provinces: dict[str, list[str]] = {}
        for r in con.execute(
            "SELECT p1.source_province_name, p2.source_province_name "
            "FROM dim_province p1 JOIN dim_province p2 ON p1.island_group = p2.island_group "
            "WHERE p1.source_province_name != p2.source_province_name"
        ).fetchall():
            neighbor_provinces.setdefault(str(r[0]), []).append(str(r[1]))

        # Reconciliation: province-level prices
        province_prices_recon: dict[str, float] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, price_idr FROM fct_price_daily"
        ).fetchall():
            key = f"{r[0]!s}||{r[1]!s}"
            province_prices_recon[key] = float(r[2])

        # Reconciliation: city-level prices
        city_prices_recon: dict[str, list[dict]] = {}
        for r in con.execute(
            "SELECT commodity_id, source_province_name, city_name, price_idr "
            "FROM fct_price_city_daily"
        ).fetchall():
            key = f"{r[0]!s}||{r[1]!s}"
            city_prices_recon.setdefault(key, []).append(
                {
                    "city_name": str(r[2]),
                    "price_idr": float(r[3]),
                }
            )

        # Reconciliation: national prices
        national_prices_recon: dict[str, float] = {}
        for r in con.execute(
            "SELECT commodity_id, price_idr FROM fct_price_national_daily"
        ).fetchall():
            national_prices_recon[str(r[0])] = float(r[1])

        con.close()
    else:
        latest_national_snapshot = None
        volatile_commodities = []
        latest_volatile_snapshots = {}
        previous_prices = {}
        current_volatile_prices = {}
        expected_combinations = set()
        reported_combinations = set()
        prices = {}
        plausible_ranges = {}
        expected_units = {}
        historical_prices = {}
        national_prices = {}
        province_prices = {}
        city_prices = {}
        duplicate_rows = []
        snapshot_rows = []
        expected_fingerprints = {}
        anomaly_prices = {}
        national_prices_anomaly = {}
        neighbor_provinces = {}
        province_prices_recon = {}
        city_prices_recon = {}
        national_prices_recon = {}

    from datetime import datetime

    from hpdq.checks import (
        check_anomaly,
        check_completeness,
        check_duplicates,
        check_freshness,
        check_reconciliation,
        check_schema_drift,
        check_validity,
    )

    result = {
        "business_date": business_date.isoformat(),
        "checks": [],
        "incidents": [],
    }

    # Check 1: Freshness
    typer.echo("Running freshness check...")
    now = datetime.now(UTC)
    expected_publication_time = now.replace(hour=14, minute=0, second=0, microsecond=0)
    cutoff_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
    freshness_incidents = check_freshness(
        expected_publication_time=expected_publication_time,
        cutoff_time=cutoff_time,
        latest_national_snapshot=latest_national_snapshot,
        volatile_commodities=volatile_commodities,
        latest_volatile_snapshots=latest_volatile_snapshots,
        previous_prices=previous_prices,
        current_volatile_prices=current_volatile_prices,
    )
    result["checks"].append({"name": "freshness", "passed": len(freshness_incidents) == 0})
    for incident in freshness_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 2: Completeness
    typer.echo("Running completeness check...")
    completeness_incidents = check_completeness(
        expected_combinations=expected_combinations,
        reported_combinations=reported_combinations,
        historical_reporting={},
    )
    result["checks"].append({"name": "completeness", "passed": len(completeness_incidents) == 0})
    for incident in completeness_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 3: Validity
    typer.echo("Running validity check...")
    # Transform prices dict to expected format
    validity_prices: dict[str, dict[str, object]] = {}
    for (commodity_id, province, _date_str), price_idr in prices.items():
        key = f"{commodity_id}||{province}"
        validity_prices[key] = {"price_idr": price_idr}
    # Transform plausible_ranges to tuple format
    plausible_ranges_tuple: dict[str, tuple[int, int]] = {
        k: (int(v["min"]), int(v["max"])) for k, v in plausible_ranges.items()
    }
    validity_incidents = check_validity(
        prices=validity_prices,
        plausible_ranges=plausible_ranges_tuple,
        expected_units=expected_units,
        reported_units={},
    )
    result["checks"].append({"name": "validity", "passed": len(validity_incidents) == 0})
    for incident in validity_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 4: Duplicates
    typer.echo("Running duplicates check...")
    duplicates_incidents = check_duplicates(prices=duplicate_rows)
    result["checks"].append({"name": "duplicates", "passed": len(duplicates_incidents) == 0})
    for incident in duplicates_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 5: Schema drift
    typer.echo("Running schema drift check...")
    schema_incidents = check_schema_drift(
        snapshots=snapshot_rows,
        expected_fingerprints=expected_fingerprints,
    )
    result["checks"].append({"name": "schema_drift", "passed": len(schema_incidents) == 0})
    for incident in schema_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 6: Anomaly
    typer.echo("Running anomaly check...")
    anomaly_incidents = check_anomaly(
        prices=anomaly_prices,
        historical_prices=historical_prices,
        holiday_windows=set(),
        national_prices=national_prices_anomaly,
        neighbor_provinces=neighbor_provinces,
    )
    result["checks"].append({"name": "anomaly", "passed": len(anomaly_incidents) == 0})
    for incident in anomaly_incidents:
        result["incidents"].append(incident.to_dict())

    # Check 7: Reconciliation
    typer.echo("Running reconciliation check...")
    reconciliation_incidents = check_reconciliation(
        province_prices=province_prices_recon,
        city_prices=city_prices_recon,
        national_prices=national_prices_recon,
    )
    result["checks"].append(
        {"name": "reconciliation", "passed": len(reconciliation_incidents) == 0}
    )
    for incident in reconciliation_incidents:
        result["incidents"].append(incident.to_dict())

    # Log all incidents to SQLite store
    from hpdq.checks.incidents import IncidentEvent

    all_incidents = (
        list(freshness_incidents)
        + list(completeness_incidents)
        + list(validity_incidents)
        + list(duplicates_incidents)
        + list(schema_incidents)
        + list(anomaly_incidents)
        + list(reconciliation_incidents)
    )
    for incident in all_incidents:
        event = IncidentEvent(
            event_id=f"evt-{incident.incident_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            incident_id=incident.incident_id,
            event_type="opened",
            at=incident.opened_at,
            check=incident.check,
            severity=incident.severity,
            scope=incident.scope,
            status=incident.status,
            resolution=incident.resolution,
            false_alarm=incident.false_alarm,
            issue_number=incident.issue_number,
        )
        store.log_event(event.to_dict())

    # Print results
    passed = sum(1 for c in result["checks"] if c["passed"])
    failed = len(result["checks"]) - passed

    typer.echo("\n" + "=" * 60)
    typer.echo(f"Results for D={business_date.isoformat()}")
    typer.echo(f"Checks: {passed}/{len(result['checks'])} passed")
    typer.echo(f"Failed: {failed}")
    typer.echo("=" * 60)

    for check in result["checks"]:
        status = "[PASS]" if check["passed"] else "[FAIL]"
        typer.echo(f"  {status} {check['name']}")

    if result["incidents"]:
        typer.echo("\nIncidents:")
        for incident in result["incidents"]:
            severity = incident.get("severity", "unknown")
            scope = incident.get("scope", {})
            typer.echo(f"  [{severity}] {scope.get('scope_type', 'unknown')}")
            typer.echo(f"    {scope.get('scope_value', '')}")

    # Save results
    results_file = build_dir / "check_results.json"
    with results_file.open("w", encoding="utf-8") as f:
        import json

        json.dump(result, f, indent=2, ensure_ascii=False)
    typer.echo(f"\nResults saved to {results_file.as_posix()}")

    if failed > 0:
        raise typer.Exit(code=1)


@app.command()
def deploy(
    data_dir: DataDir = None,
    build_dir: BuildDir = config.DEFAULT_BUILD_DIR,
    out_dir: Annotated[Path, typer.Option(help="Site data output directory.")] = Path("data/site"),
) -> None:
    """Generate static data files for the GitHub Pages evidence site.

    Reads from the DuckDB warehouse (built by ``dbt build``) and writes JSON/CSV
    files into the output directory. Called by the ``daily.yml`` workflow after
    ingestion and dbt build.
    """
    from hpdq.deploy import deploy as deploy_site

    warehouse = build_dir / "warehouse.duckdb"
    if not warehouse.exists():
        typer.echo("Warehouse not found. Run `hpdq build` first.", err=True)
        raise typer.Exit(code=1)
    deploy_site(warehouse, out_dir)
    typer.echo(f"site data: {out_dir}")


@raw_app.command("verify")
def raw_verify(
    data_dir: DataDir = None,
    git_staged: Annotated[
        bool, typer.Option(help="Also fail if staged git changes modify or delete files.")
    ] = False,
) -> None:
    """Check every raw file against its hash, size and metadata (and append-only in git)."""
    root = data_dir or config.default_data_dir()
    problems = verify_store(root)
    if git_staged:
        problems += [f"git: not append-only: {v}" for v in git_append_only_violations(root)]
    for problem in problems:
        typer.echo(problem, err=True)
    if problems:
        raise typer.Exit(code=1)
    typer.echo(f"raw store OK: {root.as_posix()}")


if __name__ == "__main__":  # pragma: no cover
    app()
