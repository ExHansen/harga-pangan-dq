"""``hpdq`` command-line interface."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from hpdq import __version__, config
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
