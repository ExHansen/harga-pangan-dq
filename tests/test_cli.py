from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from hpdq import cli, config
from hpdq.pihps.client import PihpsClient
from support import FakeTime, MockPihps

runner = CliRunner()


@pytest.fixture
def offline_client(monkeypatch: pytest.MonkeyPatch, fake_time: FakeTime) -> MockPihps:
    """Make ``hpdq ingest`` talk to the fixture-backed mock instead of the internet."""
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


def test_version_shows_the_user_agent() -> None:
    result = runner.invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert config.user_agent() in result.output


def test_dry_run_prints_the_plan_without_network() -> None:
    result = runner.invoke(cli.app, ["ingest", "--date", "2026-11-11", "--dry-run"])

    assert result.exit_code == 0
    assert result.output.count("GET https://www.bi.go.id/") == 6
    assert "start_date=2026-11-04&end_date=2026-11-11" in result.output


def test_unknown_group_is_a_usage_error() -> None:
    result = runner.invoke(cli.app, ["ingest", "--group", "durian", "--dry-run"])

    assert result.exit_code == 2


def test_ingest_twice_then_verify_and_load(tmp_path: Path, offline_client: MockPihps) -> None:
    data = tmp_path / "data"
    args = ["ingest", "--date", "2026-11-11", "--data-dir", str(data)]

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


def test_refused_run_exits_non_zero(tmp_path: Path, offline_client: MockPihps) -> None:
    offline_client.overrides["com_13"] = lambda r: httpx.Response(403)

    result = runner.invoke(cli.app, ["ingest", "--date", "2026-11-11", "--data-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "partial" in result.output
