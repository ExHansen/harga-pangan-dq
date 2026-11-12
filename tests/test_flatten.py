import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from hpdq.load.flatten import build_parsed
from hpdq.pihps.specs import RequestSpec, commodity_grid, ref_commodities, ref_provinces
from hpdq.raw.store import RawStore
from support import CHILLIES, START, fixture_bytes, grid_fixture_name, make_result

WINDOW = (date(2026, 11, 4), date(2026, 11, 11))


def fixture_specs() -> list[tuple[RequestSpec, str]]:
    pairs = [(ref_commodities(), "ref_commodities.json"), (ref_provinces(), "ref_provinces.json")]
    pairs += [(commodity_grid(c, *WINDOW), grid_fixture_name(c)) for c in CHILLIES]
    return pairs


@pytest.fixture
def seeded_root(tmp_path: Path) -> Path:
    # An apostrophe in the path proves file names are quoted safely in the generated SQL.
    root = tmp_path / "it's data"
    store = RawStore(root)
    for i, (spec, name) in enumerate(fixture_specs()):
        fetched_at = START + timedelta(seconds=3 * i)
        store.put(make_result(spec, fixture_bytes(name), fetched_at), run_id="r")
    return root


def query(path: Path, sql: str) -> list[tuple[Any, ...]]:
    con = duckdb.connect()
    try:
        return con.execute(sql.replace("$t", f"'{path.as_posix()}'")).fetchall()
    finally:
        con.close()


def test_every_value_of_every_row_survives_the_round_trip(
    seeded_root: Path, tmp_path: Path
) -> None:
    summary = build_parsed(seeded_root, tmp_path / "out")
    snapshot_ids = dict(query(summary.snapshots_path, "select request_key, snapshot_id from $t"))
    cells = query(summary.cells_path, "select snapshot_id, row_idx, field, value_json from $t")

    rebuilt: dict[str, dict[int, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for snapshot_id, row_idx, field, value_json in cells:
        rebuilt[snapshot_id][row_idx][field] = json.loads(value_json)

    expected_cells = 0
    for spec, name in fixture_specs():
        original = json.loads(fixture_bytes(name))["data"]
        rows = rebuilt[snapshot_ids[spec.key]]
        assert [rows[i] for i in range(len(rows))] == original, name
        expected_cells += sum(len(row) for row in original)

    assert (summary.snapshots, summary.ok, summary.not_ok) == (6, 6, 0)
    assert summary.cells == expected_cells == len(cells)


def test_row_order_is_kept_so_cities_can_find_their_province(
    seeded_root: Path, tmp_path: Path
) -> None:
    summary = build_parsed(seeded_root, tmp_path / "out")

    rows = dict(
        query(
            summary.cells_path,
            "select value_text, row_idx from $t "
            "where snapshot_id like 'com_13%' and field = 'name' "
            "and value_text in ('Kalimantan Barat', 'Kota Pontianak')",
        )
    )

    assert rows["Kota Pontianak"] == rows["Kalimantan Barat"] + 1


def test_values_are_kept_as_text_without_interpretation(seeded_root: Path, tmp_path: Path) -> None:
    summary = build_parsed(seeded_root, tmp_path / "out")

    (national,) = query(
        summary.cells_path,
        "select value_json, value_type, value_text from $t "
        "where snapshot_id like 'com_13%' and row_idx = 0 and field = '04/11/2026'",
    )
    missing = query(
        summary.cells_path,
        "select count(*) from $t where value_text = '-' and value_json = '\"-\"'",
    )

    assert national == ('"70,250"', "VARCHAR", "70,250")
    assert missing[0][0] > 0


def test_broken_snapshot_is_recorded_but_not_flattened(seeded_root: Path, tmp_path: Path) -> None:
    broken = commodity_grid("com_1", *WINDOW)
    RawStore(seeded_root).put(
        make_result(broken, b"<html>Request Rejected</html>", START), run_id="r"
    )

    summary = build_parsed(seeded_root, tmp_path / "out")

    statuses = dict(query(summary.snapshots_path, "select request_key, status from $t"))
    assert statuses[broken.key] == "invalid_json"
    assert (summary.ok, summary.not_ok) == (6, 1)
    broken_cells = "select count(*) from $t where starts_with(snapshot_id, 'com_1__')"
    assert query(summary.cells_path, broken_cells) == [(0,)]


def test_empty_store_gives_empty_tables_with_schema(tmp_path: Path) -> None:
    summary = build_parsed(tmp_path / "empty", tmp_path / "out")

    assert (summary.snapshots, summary.cells) == (0, 0)
    columns = [c[0] for c in query(summary.cells_path, "describe select * from $t")]
    assert columns == ["snapshot_id", "row_idx", "field", "value_json", "value_type", "value_text"]


def test_rebuild_is_deterministic(seeded_root: Path, tmp_path: Path) -> None:
    first = build_parsed(seeded_root, tmp_path / "a")
    second = build_parsed(seeded_root, tmp_path / "b")

    cells_sql = "select * from $t"
    # TIMESTAMPTZ -> text: fetching it as a Python datetime would need the pytz package.
    snaps_sql = "select * replace (cast(fetched_at as varchar) as fetched_at) from $t"
    assert query(first.cells_path, cells_sql) == query(second.cells_path, cells_sql)
    assert query(first.snapshots_path, snaps_sql) == query(second.snapshots_path, snaps_sql)
