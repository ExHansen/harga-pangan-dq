from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from hpdq import cli, config
from hpdq.pihps.client import PihpsClient
from support import FakeTime, MockPihps

runner = CliRunner()
CHILLIES = ["--group", "chillies"]


@pytest.fixture
def offline_client(monkeypatch: pytest.MonkeyPatch, fake_time: FakeTime) -> MockPihps:
    """Make the CLI talk to the fixture-backed mock instead of the internet."""
    mock = MockPihps()
    original_create = PihpsClient.create

    def create(**kwargs: object) -> PihpsClient:
        return original_create(
            transport=httpx.MockTransport(mock),
            sleep=fake_time.sleep,
            monotonic=fake_time.monotonic,
            clock=fake_time.clock,
        )

    monkeypatch.setattr(PihpsClient, "create", staticmethod(create))
    return mock


def gets(output: str) -> int:
    return output.count("GET https://www.bi.go.id/")


def test_version_shows_the_user_agent() -> None:
    result = runner.invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert config.user_agent() in result.output


def test_dry_run_prints_the_plan_without_network() -> None:
    default = runner.invoke(cli.app, ["ingest", "--date", "2026-11-11", "--dry-run"])
    chillies = runner.invoke(cli.app, ["ingest", "--date", "2026-11-11", "--dry-run", *CHILLIES])
    two = runner.invoke(
        cli.app,
        ["ingest", "--dry-run", "--commodity", "com_13", "--commodity", "com_16"],
    )

    assert default.exit_code == chillies.exit_code == two.exit_code == 0
    assert gets(default.output) == 2 + 21  # reference lists + every commodity
    assert gets(chillies.output) == 2 + 4
    assert gets(two.output) == 2 + 2
    assert "start_date=2026-11-04&end_date=2026-11-11" in chillies.output


@pytest.mark.parametrize(
    "args",
    [["--group", "durian"], ["--commodity", "com_99"]],
)
def test_unknown_commodities_are_a_usage_error(args: list[str]) -> None:
    result = runner.invoke(cli.app, ["ingest", "--dry-run", *args])

    assert result.exit_code == 2


def test_backfill_plans_one_request_per_commodity_per_month() -> None:
    result = runner.invoke(
        cli.app,
        ["backfill", "--start", "2026-08-15", "--end", "2026-10-03", "--dry-run", *CHILLIES],
    )

    assert result.exit_code == 0
    assert gets(result.output) == 3 * 4  # Aug (15-31), Sep, Oct (1-3) x 4 chillies
    assert "start_date=2026-08-15&end_date=2026-08-31" in result.output
    assert "start_date=2026-10-01&end_date=2026-10-03" in result.output


def test_ingest_twice_then_verify_and_load(tmp_path: Path, offline_client: MockPihps) -> None:
    data = tmp_path / "data"
    args = ["ingest", "--date", "2026-11-11", "--data-dir", str(data), *CHILLIES]

    first = runner.invoke(cli.app, [*args, "--run-id", "one"])
    second = runner.invoke(cli.app, [*args, "--run-id", "two"])
    verify = runner.invoke(cli.app, ["raw", "verify", "--data-dir", str(data)])
    load = runner.invoke(
        cli.app, ["load", "--data-dir", str(data), "--out-dir", str(tmp_path / "parsed")]
    )

    assert first.exit_code == 0, first.output
    assert "stored 6, unchanged 0" in first.output
    assert second.exit_code == 0, second.output
    assert "stored 0, unchanged 6" in second.output
    assert verify.exit_code == 0 and "raw store OK" in verify.output
    assert load.exit_code == 0 and "snapshots 6 (ok 6, not ok 0)" in load.output


def test_backfill_resumes_without_asking_the_source_again(
    tmp_path: Path, offline_client: MockPihps
) -> None:
    args = ["backfill", "--start", "2026-10-01", "--end", "2026-11-11", "--data-dir", str(tmp_path)]

    first = runner.invoke(cli.app, [*args, *CHILLIES, "--run-id", "one"])
    calls_after_first = len(offline_client.calls)
    second = runner.invoke(cli.app, [*args, *CHILLIES, "--run-id", "two"])

    assert first.exit_code == 0, first.output
    assert "stored 8" in first.output  # 2 months x 4 chillies
    assert second.exit_code == 0, second.output
    assert "already stored 8" in second.output
    assert len(offline_client.calls) == calls_after_first  # no request at all the second time


def test_refused_run_exits_non_zero(tmp_path: Path, offline_client: MockPihps) -> None:
    offline_client.overrides["com_13"] = lambda r: httpx.Response(403)

    result = runner.invoke(
        cli.app, ["ingest", "--date", "2026-11-11", "--data-dir", str(tmp_path), *CHILLIES]
    )

    assert result.exit_code == 1
    assert "partial" in result.output
