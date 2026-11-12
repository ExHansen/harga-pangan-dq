import json

import pytest

from hpdq.load.inspect import inspect_payload
from support import CHILLIES, fixture_bytes, fixture_json, grid_fixture_name


@pytest.mark.parametrize("comcat_id", CHILLIES)
def test_recorded_grids_have_the_expected_shape(comcat_id: str) -> None:
    fp = inspect_payload(fixture_bytes(grid_fixture_name(comcat_id)))

    assert fp.status == "ok"
    assert fp.top_level_keys == ("data",)
    assert fp.row_keys == ("level", "name", "no")
    assert fp.date_key_count == 6  # 04-06 and 09-11 Nov 2026; no weekend columns
    assert fp.levels == ("0", "1", "2")  # national, province, city
    assert fp.value_types == ("string",)


def test_recorded_reference_lists() -> None:
    commodities = inspect_payload(fixture_bytes("ref_commodities.json"))
    provinces = inspect_payload(fixture_bytes("ref_provinces.json"))

    assert commodities.row_keys == ("cat_id", "denomination", "id", "name", "sort")
    assert commodities.row_count == 31  # 10 categories + 21 commodities
    assert provinces.row_keys == ("id", "name")
    assert provinces.row_count == 34  # pre-2022 province list


def grid_with(mutate: object) -> bytes:
    doc = fixture_json(grid_fixture_name("com_13"))
    assert callable(mutate)
    mutate(doc)
    return json.dumps(doc).encode()


def test_renamed_column_is_visible_in_the_fingerprint() -> None:
    def rename(doc: dict) -> None:  # type: ignore[type-arg]
        for row in doc["data"]:
            row["nama"] = row.pop("name")

    fp = inspect_payload(grid_with(rename))

    assert fp.status == "ok"  # judging drift is the schema-drift check's job (M3)
    assert fp.row_keys == ("level", "nama", "no")


def test_numeric_prices_change_the_value_types() -> None:
    def to_numbers(doc: dict) -> None:  # type: ignore[type-arg]
        doc["data"][0]["04/11/2026"] = 70250

    assert inspect_payload(grid_with(to_numbers)).value_types == ("number", "string")


@pytest.mark.parametrize(
    ("body", "status", "error_part"),
    [
        (b"<html><body>Request Rejected</body></html>", "invalid_json", "JSONDecodeError"),
        (b"\xff\xfe\x00garbage", "invalid_json", "Error"),
        (b"[]", "unexpected_shape", "top level is array"),
        (b'{"rows": []}', "unexpected_shape", "'data' is missing"),
        (b'{"data": {"a": 1}}', "unexpected_shape", "'data' is object"),
        (b'{"data": [{"name": "x"}, 5]}', "unexpected_shape", "row 1 is number"),
    ],
)
def test_broken_payloads_are_findings_not_crashes(
    body: bytes, status: str, error_part: str
) -> None:
    fp = inspect_payload(body)

    assert fp.status == status
    assert fp.error is not None and error_part in fp.error


def test_empty_result_is_valid() -> None:
    fp = inspect_payload(b'{"data":[]}')  # what PIHPS returns for a window with no data

    assert (fp.status, fp.row_count, fp.date_key_count) == ("ok", 0, 0)
