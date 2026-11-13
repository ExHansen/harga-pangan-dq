"""Request specifications for the PIHPS endpoints.

These are the public, unauthenticated GET endpoints that the PIHPS "Tabel Harga" pages call
themselves (docs/phase0-source-discovery.md, ADR-001). A spec is a pure value: building one never
touches the network, so plans can be printed (``hpdq ingest --dry-run``) and tested offline.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

BASE_URL = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga"

PRICE_TYPE_TRADITIONAL = 1  # 1 traditional, 2 modern, 3 wholesaler, 4 producer
REPORT_DAILY = 1  # tipe_laporan: 1 daily, 4 weekly, 5 monthly, 6 chart


class Endpoint(StrEnum):
    COMMODITY_GRID = "GetGridDataKomoditas"
    REF_COMMODITIES = "GetRefCommodityAndCategory"
    REF_PROVINCES = "GetRefProvince"


@dataclass(frozen=True)
class RequestSpec:
    """One GET request, plus where its responses are stored.

    ``partition`` is the folder under ``raw/pihps/``; ``key`` identifies the request inside it and
    starts every stored file name, so all snapshots of the same request sort together.
    """

    endpoint: Endpoint
    params: tuple[tuple[str, str], ...]
    partition: str
    key: str

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.endpoint.value}"

    def params_dict(self) -> dict[str, str]:
        return dict(self.params)


def commodity_grid(
    comcat_id: str,
    start: date,
    end: date,
    *,
    price_type_id: int = PRICE_TYPE_TRADITIONAL,
    show_kota: bool = True,
) -> RequestSpec:
    """All provinces (and, with ``show_kota``, their sample cities) for one commodity and window.

    The response also carries the national row ("Semua Provinsi"), so one request per commodity
    covers the whole country.
    """
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    params = (
        ("price_type_id", str(price_type_id)),
        ("comcat_id", comcat_id),
        ("province_id", ""),
        ("regency_id", ""),
        ("showKota", "true" if show_kota else "false"),
        ("showPasar", "false"),
        ("tipe_laporan", str(REPORT_DAILY)),
        ("start_date", start.isoformat()),
        ("end_date", end.isoformat()),
    )
    key = f"{comcat_id}__{start:%Y%m%d}-{end:%Y%m%d}__k{int(show_kota)}"
    return RequestSpec(
        endpoint=Endpoint.COMMODITY_GRID,
        params=params,
        partition=f"komoditas/price_type={price_type_id}",
        key=key,
    )


def ref_commodities() -> RequestSpec:
    return RequestSpec(Endpoint.REF_COMMODITIES, (), "ref", "commodities")


def ref_provinces() -> RequestSpec:
    return RequestSpec(Endpoint.REF_PROVINCES, (), "ref", "provinces")


def daily_window(business_date: date, window_days: int) -> tuple[date, date]:
    """``(D - window_days, D)``. Calendar days: weekends simply come back without columns."""
    if window_days < 0:
        raise ValueError("window_days must be >= 0")
    return business_date - timedelta(days=window_days), business_date


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Split ``[start, end]`` (inclusive) at calendar-month boundaries.

    Why months: the source's response time grows with the window (8 days ~3 s, 31 days ~5 s,
    one year > 30 s and timed out, measured 2026-11-12), so backfill asks for one month at a time.
    Month-aligned windows also give stable, readable request keys, which makes backfill resumable.
    """
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    windows = []
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
        window_end = min(next_month - timedelta(days=1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def plan_backfill(
    start: date,
    end: date,
    comcat_ids: tuple[str, ...],
    *,
    show_kota: bool = True,
) -> list[RequestSpec]:
    """One grid request per commodity per month. No reference lists: they describe today only."""
    return [
        commodity_grid(c, w_start, w_end, show_kota=show_kota)
        for w_start, w_end in month_windows(start, end)
        for c in comcat_ids
    ]


def plan_daily(
    business_date: date,
    comcat_ids: tuple[str, ...],
    *,
    window_days: int,
    show_kota: bool = True,
) -> list[RequestSpec]:
    """Reference lists first (they feed the schema-drift and unit checks), then one grid each."""
    start, end = daily_window(business_date, window_days)
    specs = [ref_commodities(), ref_provinces()]
    specs += [commodity_grid(c, start, end, show_kota=show_kota) for c in comcat_ids]
    return specs
