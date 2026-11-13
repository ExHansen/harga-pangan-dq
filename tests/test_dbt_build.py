"""Integration: recorded fixtures -> raw store -> load -> `dbt build` (seeds, models, all tests,
unit tests, contracts) -> spot-check mart values that can be verified by hand from the fixtures."""

import json
import socket
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import duckdb
import pytest

from hpdq.load.flatten import build_parsed
from hpdq.pihps.specs import commodity_grid, ref_commodities, ref_provinces
from hpdq.raw.store import RawStore
from hpdq.transform import DbtPaths, run_dbt
from support import CHILLIES, START, block_network, fixture_bytes, grid_fixture_name, make_result

WINDOW = (date(2026, 11, 4), date(2026, 11, 11))


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Iterator[duckdb.DuckDBPyConnection]:
    # Module-scoped fixtures run before the function-scoped network guard, so block it here too.
    with pytest.MonkeyPatch.context() as mp:
        for target, name in [(socket.socket, "connect"), (socket, "create_connection")]:
            mp.setattr(target, name, block_network)

        tmp = tmp_path_factory.mktemp("dbt")
        store = RawStore(tmp / "data")
        pairs = [
            (ref_commodities(), "ref_commodities.json"),
            (ref_provinces(), "ref_provinces.json"),
        ]
        pairs += [(commodity_grid(c, *WINDOW), grid_fixture_name(c)) for c in CHILLIES]
        for i, (spec, name) in enumerate(pairs):
            fetched_at = START + timedelta(seconds=3 * i)
            store.put(make_result(spec, fixture_bytes(name), fetched_at), run_id="fixture")

        paths = DbtPaths.under(tmp / "build")
        build_parsed(tmp / "data", paths.parsed_dir)
        assert run_dbt(["build"], paths), "dbt build failed; see build/dbt/logs in the tmp dir"

    con = duckdb.connect(str(paths.warehouse), read_only=True)
    yield con
    con.close()


def one(con: duckdb.DuckDBPyConnection, sql: str, *params: Any) -> Any:
    row = con.execute(sql, list(params)).fetchone()
    assert row is not None
    return row[0] if len(row) == 1 else row


def fixture_rows(comcat_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(fixture_bytes(grid_fixture_name(comcat_id)))["data"]
    return rows


def test_national_price_is_the_source_figure(warehouse: duckdb.DuckDBPyConnection) -> None:
    national = one(
        warehouse,
        "select price_idr from fct_price_national_daily "
        "where commodity_id = 'com_13' and price_date = date '2026-11-04'",
    )
    assert national == 70250  # "70,250" in grid_com_13 row 0


def test_every_observed_province_price_reaches_the_mart(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    expected = sum(
        1
        for c in CHILLIES
        for row in fixture_rows(c)
        if row["level"] == 1
        for key, value in row.items()
        if "/" in key and value != "-"
    )
    assert one(warehouse, "select count(*) from fct_price_daily") == expected


def test_day_over_day_and_gap_to_national(warehouse: duckdb.DuckDBPyConnection) -> None:
    papua = {r["name"]: r for r in fixture_rows("com_13") if r["level"] <= 1}["Papua"]
    national = fixture_rows("com_13")[0]
    p10, p11 = (int(papua[d].replace(",", "")) for d in ("10/11/2026", "11/11/2026"))
    n11 = int(national["11/11/2026"].replace(",", ""))

    dod, gap, days = one(
        warehouse,
        "select dod_pct, gap_to_national_pct, days_since_prev from fct_price_daily "
        "where commodity_id = 'com_13' and source_province_name = 'Papua' "
        "and price_date = date '2026-11-11'",
    )

    assert dod == pytest.approx(100 * (p11 / p10 - 1))
    assert gap == pytest.approx(100 * (p11 / n11 - 1))
    assert days == 1


def test_monday_compares_with_friday(warehouse: duckdb.DuckDBPyConnection) -> None:
    prev, days = one(
        warehouse,
        "select prev_price_date, days_since_prev from fct_price_national_daily "
        "where commodity_id = 'com_13' and price_date = date '2026-11-09'",
    )
    assert (prev, days) == (date(2026, 11, 6), 3)


def test_split_province_cities_land_in_their_current_province(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = dict(
        warehouse.execute(
            "select distinct city_name, province_iso_code from fct_price_city_daily "
            "where source_province_name in ('Papua', 'Papua Barat')"
        ).fetchall()
    )
    assert rows["Kota Sorong"] == "ID-PD"
    assert rows["Kab. Merauke"] == "ID-PS"
    assert rows["Kab. Jayawijaya"] == "ID-PE"
    assert rows["Kota Jayapura"] == "ID-PA"


def test_province_reference_covers_38_and_34(warehouse: duckdb.DuckDBPyConnection) -> None:
    assert one(warehouse, "select count(*) from dim_province") == 38
    assert one(warehouse, "select count(*) from dim_province where source_province_id is null") == 0
    assert one(warehouse, "select count(*) from dim_source_province") == 34
    assert (
        one(
            warehouse,
            "select current_province_count from dim_source_province "
            "where source_province_name = 'Papua'",
        )
        == 4
    )


def test_cooking_oil_unit_discrepancy_is_visible(warehouse: duckdb.DuckDBPyConnection) -> None:
    unit, source_unit, note = one(
        warehouse,
        "select unit, source_denomination, unit_note from dim_commodity "
        "where commodity_id = 'com_17'",
    )
    assert (unit, source_unit) == ("kg", "kg")
    assert "litre" in note
