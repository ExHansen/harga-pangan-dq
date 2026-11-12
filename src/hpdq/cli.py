"""``hpdq`` command-line interface."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from hpdq import __version__, config
from hpdq.ingest import run_ingest
from hpdq.load.flatten import build_parsed
from hpdq.pihps.catalog import DEFAULT_GROUP, commodities_for
from hpdq.pihps.client import PihpsClient
from hpdq.pihps.specs import plan_daily
from hpdq.raw.store import RawStore
from hpdq.raw.verify import git_append_only_violations, verify_store
from hpdq.timeutil import now_utc, wib_date

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


@app.callback()
def _main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _business_date(value: datetime | None) -> date:
    return value.date() if value is not None else wib_date(now_utc())


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
    group: Annotated[str, typer.Option(help="Commodity group to fetch.")] = DEFAULT_GROUP,
    window_days: Annotated[
        int, typer.Option(min=0, max=31, help="Fetch D-window_days..D.")
    ] = config.DEFAULT_WINDOW_DAYS,
    show_kota: Annotated[bool, typer.Option(help="Include city rows.")] = True,
    data_dir: DataDir = None,
    run_id: Annotated[str | None, typer.Option(help="Default: GitHub run id or random.")] = None,
    dry_run: Annotated[bool, typer.Option(help="Print the plan; no network.")] = False,
) -> None:
    """Fetch one business day's window from PIHPS and store new responses immutably."""
    business_date = _business_date(date_)
    try:
        comcat_ids = commodities_for(group)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--group") from None
    specs = plan_daily(business_date, comcat_ids, window_days=window_days, show_kota=show_kota)

    if dry_run:
        typer.echo(f"Plan for D={business_date} ({len(specs)} requests, >= 3 s apart):")
        for spec in specs:
            query = "&".join(f"{k}={v}" for k, v in spec.params)
            typer.echo(f"  GET {spec.url}{'?' + query if query else ''}")
        return

    root = data_dir or config.default_data_dir()
    rid = run_id or config.default_run_id()
    with PihpsClient.create() as client:
        summary = run_ingest(
            specs, business_date=business_date, client=client, store=RawStore(root), run_id=rid
        )
    typer.echo(
        f"run {summary.run_id} D={summary.business_date}: {summary.status} | "
        f"planned {summary.planned}, stored {summary.stored}, unchanged {summary.deduped}, "
        f"failed {summary.failed}, skipped {summary.skipped}, http attempts {summary.http_attempts}"
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
