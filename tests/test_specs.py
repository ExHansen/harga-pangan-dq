from datetime import date

import pytest

from hpdq.pihps.catalog import COMMODITY_GROUPS, commodities_for
from hpdq.pihps.specs import Endpoint, commodity_grid, daily_window, plan_daily

D = date(2026, 11, 11)


def test_daily_plan_fetches_refs_first_then_one_grid_per_commodity() -> None:
    specs = plan_daily(D, commodities_for("chillies"), window_days=7)

    assert [s.endpoint for s in specs] == [
        Endpoint.REF_COMMODITIES,
        Endpoint.REF_PROVINCES,
        *[Endpoint.COMMODITY_GRID] * 4,
    ]
    assert len({s.key for s in specs}) == len(specs)


def test_grid_params_cover_window_traditional_market_daily_with_cities() -> None:
    spec = plan_daily(D, ("com_13",), window_days=7)[-1]

    assert spec.params_dict() == {
        "price_type_id": "1",
        "comcat_id": "com_13",
        "province_id": "",
        "regency_id": "",
        "showKota": "true",
        "showPasar": "false",
        "tipe_laporan": "1",
        "start_date": "2026-11-04",
        "end_date": "2026-11-11",
    }
    assert spec.partition == "komoditas/price_type=1"
    assert spec.key == "com_13__20261104-20261111__k1"
    assert spec.url.endswith("/hargapangan/WebSite/TabelHarga/GetGridDataKomoditas")


def test_key_distinguishes_city_level_requests() -> None:
    with_cities = commodity_grid("com_13", D, D, show_kota=True)
    provinces_only = commodity_grid("com_13", D, D, show_kota=False)

    assert with_cities.key != provinces_only.key


def test_window_rejects_negative_and_inverted_ranges() -> None:
    assert daily_window(D, 0) == (D, D)
    with pytest.raises(ValueError):
        daily_window(D, -1)
    with pytest.raises(ValueError):
        commodity_grid("com_13", D, date(2026, 11, 1))


def test_commodity_groups() -> None:
    assert commodities_for("chillies") == ("com_13", "com_14", "com_15", "com_16")
    assert len(COMMODITY_GROUPS["all"]) == 21
    with pytest.raises(ValueError, match="unknown commodity group"):
        commodities_for("durian")
