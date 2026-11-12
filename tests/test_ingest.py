import json
from datetime import date
from pathlib import Path

import httpx

from hpdq.ingest import IngestSummary, run_ingest
from hpdq.pihps.specs import plan_daily
from hpdq.raw.store import RawStore
from support import CHILLIES, FakeTime, MockPihps

D = date(2026, 11, 11)
SPECS = plan_daily(D, CHILLIES, window_days=7)


def raw_files(root: Path) -> list[Path]:
    return sorted((root / "raw").rglob("*.json.gz"))


def manifest_outcomes(summary: IngestSummary) -> list[str]:
    assert summary.manifest_path is not None
    lines = summary.manifest_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["outcome"] for line in lines]


def ingest(root: Path, mock: MockPihps, time: FakeTime, run_id: str) -> IngestSummary:
    with mock.client(time) as client:
        return run_ingest(
            SPECS,
            business_date=D,
            client=client,
            store=RawStore(root),
            run_id=run_id,
            clock=time.clock,
        )


def test_first_run_stores_everything_second_run_stores_nothing(
    tmp_path: Path, mock_pihps: MockPihps, fake_time: FakeTime
) -> None:
    first = ingest(tmp_path, mock_pihps, fake_time, "run-1")
    after_first = raw_files(tmp_path)

    second = ingest(tmp_path, mock_pihps, fake_time, "run-2")

    assert (first.status, first.stored, first.deduped) == ("success", 6, 0)
    assert (second.status, second.stored, second.deduped) == ("success", 0, 6)
    assert len(after_first) == 6
    assert raw_files(tmp_path) == after_first
    assert manifest_outcomes(first) == ["stored"] * 6
    assert manifest_outcomes(second) == ["dedup"] * 6
    assert first.manifest_path != second.manifest_path


def test_refusal_stops_the_run_and_skips_the_rest(tmp_path: Path, fake_time: FakeTime) -> None:
    mock = MockPihps(overrides={"com_14": lambda r: httpx.Response(429)})

    summary = ingest(tmp_path, mock, fake_time, "run-1")

    assert summary.status == "partial"
    assert (summary.stored, summary.failed, summary.skipped) == (3, 1, 2)
    assert summary.stop_reason is not None and "429" in summary.stop_reason
    assert manifest_outcomes(summary) == ["stored"] * 3 + ["refused", "skipped", "skipped"]
    assert len(mock.calls) == 4  # nothing was requested after the refusal


def test_a_failed_request_does_not_stop_the_others(tmp_path: Path, fake_time: FakeTime) -> None:
    mock = MockPihps(overrides={"com_14": lambda r: httpx.Response(404)})

    summary = ingest(tmp_path, mock, fake_time, "run-1")

    assert summary.status == "partial"
    assert (summary.stored, summary.failed, summary.skipped) == (5, 1, 0)
    assert manifest_outcomes(summary).count("failed") == 1


def test_everything_failing_is_a_failed_run(tmp_path: Path, fake_time: FakeTime) -> None:
    mock = MockPihps(
        overrides={
            k: (lambda r: httpx.Response(404))
            for k in ["GetRefCommodityAndCategory", "GetRefProvince", *CHILLIES]
        }
    )

    summary = ingest(tmp_path, mock, fake_time, "run-1")

    assert summary.status == "failed"
    assert raw_files(tmp_path) == []
    assert summary.manifest_path is not None and summary.manifest_path.exists()
