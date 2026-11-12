import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from hpdq.pihps.specs import commodity_grid
from hpdq.raw.store import RawStore, gzip_deterministic, sha256_hex, write_new_file
from support import START, fixture_bytes, grid_fixture_name, make_result

D = date(2026, 11, 11)
SPEC = commodity_grid("com_13", date(2026, 11, 4), D)
BODY = fixture_bytes(grid_fixture_name("com_13"))


def files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_put_writes_compressed_body_and_metadata(tmp_path: Path) -> None:
    store = RawStore(tmp_path)

    put = store.put(make_result(SPEC, BODY), run_id="r1")

    sha = sha256_hex(BODY)
    expected_stem = f"com_13__20261104-20261111__k1__20261112T072000Z__{sha[:12]}"
    folder = "raw/pihps/komoditas/price_type=1/fetched=2026-11-12"
    assert put.created
    assert files(tmp_path) == [
        f"{folder}/{expected_stem}.json.gz",
        f"{folder}/{expected_stem}.meta.json",
    ]
    assert gzip.decompress(put.snapshot.body_path.read_bytes()) == BODY
    meta = json.loads(put.snapshot.meta_path.read_text(encoding="utf-8"))
    assert meta["sha256"] == sha
    assert meta["bytes"] == len(BODY)
    assert meta["params"]["comcat_id"] == "com_13"
    assert meta["fetched_at"] == "2026-11-12T07:20:00Z"
    assert meta["run_id"] == "r1"


def test_gzip_is_deterministic() -> None:
    once, twice = gzip_deterministic(BODY), gzip_deterministic(BODY)

    assert once == twice
    assert once[4:8] == b"\x00\x00\x00\x00"  # gzip header mtime field is zero


def test_same_content_again_writes_nothing(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    first = store.put(make_result(SPEC, BODY, START), run_id="r1")
    before = files(tmp_path)

    again = store.put(make_result(SPEC, BODY, START + timedelta(hours=3)), run_id="r2")

    assert not again.created
    assert again.snapshot == first.snapshot
    assert files(tmp_path) == before


def test_revision_is_a_new_snapshot_and_revert_is_kept_in_order(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    a, b = BODY, BODY.replace(b'"70,250"', b'"70,300"', 1)
    assert a != b

    results = [
        store.put(make_result(SPEC, body, START + timedelta(minutes=i)), run_id=f"r{i}")
        for i, body in enumerate([a, b, a])
    ]

    assert [r.created for r in results] == [True, True, True]
    shas = [s.sha12 for s in store.snapshots_for(SPEC)]
    assert shas == [sha256_hex(a)[:12], sha256_hex(b)[:12], sha256_hex(a)[:12]]


def test_different_requests_never_dedup_against_each_other(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    com_1 = commodity_grid("com_1", date(2026, 11, 4), D)
    com_13 = SPEC

    assert store.put(make_result(com_1, BODY), run_id="r").created
    assert store.put(make_result(com_13, BODY), run_id="r").created
    # "com_1__*" must not pick up "com_13__*"
    assert [s.key for s in store.snapshots_for(com_1)] == [com_1.key]


def test_partition_uses_the_wib_date_of_the_fetch(tmp_path: Path) -> None:
    late_evening_utc = datetime(2026, 11, 12, 18, 30, tzinfo=UTC)  # 01:30 WIB on 13 Nov

    put = RawStore(tmp_path).put(make_result(SPEC, BODY, late_evening_utc), run_id="r")

    assert put.snapshot.body_path.parent.name == "fetched=2026-11-13"


def test_write_new_file_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "a" / "file.bin"
    write_new_file(target, b"original")

    with pytest.raises(FileExistsError):
        write_new_file(target, b"replacement")

    assert target.read_bytes() == b"original"
    assert files(tmp_path) == ["a/file.bin"]  # no temp file left behind
