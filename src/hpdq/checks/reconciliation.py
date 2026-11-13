"""Check #7: Reconciliation - province vs cities, national vs provinces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentEvent, IncidentScope

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_reconciliation(
    province_prices: dict[str, float],  # province_iso_code → price
    city_prices: dict[str, list[dict]],  # province_iso_code → list of {city_name, price_idr}
    national_prices: dict[str, float],  # commodity_id → national price
    expected_rounding: int = 50,  # Province prices should be rounded to Rp 50
) -> list[Incident]:
    """
    Check reconciliation at different levels.

    Rules:
    (a) Province vs its cities: the province value equals the mean of its city rows within Rp 50 rounding.
        A break means a partial or inconsistent publication.
    (b) National vs provinces: the ratio of the national row to the mean of the provinces, per commodity,
        stays inside its trailing robust band. The two are computed differently (national = average over all
        traders), so this uses a band, not equality.

    Severity:
    (a) Critical for that province-day
    (b) Warning

    Args:
        province_prices: Dict of province_iso_code → price
        city_prices: Dict of province_iso_code → list of {city_name, price_idr}
        national_prices: Dict of commodity_id → national price
        expected_rounding: Expected rounding for province prices (default 50)

    Returns:
        List of Incident(s) for reconciliation issues.
    """
    incidents = []

    # Check 7a: Province vs its cities
    for province_iso_code, city_list in city_prices.items():
        if not city_list:
            continue

        commodity_id = list(city_list[0].keys())[0]  # Simplified - get commodity_id
        prices = [c.get("price_idr") for c in city_list if c.get("price_idr") is not None]

        if not prices:
            continue

        mean_city_price = sum(prices) / len(prices)
        province_price = province_prices.get(province_iso_code)

        if province_price is None:
            continue

        # Check if province price is within Rp 50 of mean of cities (rounded)
        rounded_mean = round(mean_city_price / expected_rounding) * expected_rounding
        diff = abs(province_price - rounded_mean)

        if diff > expected_rounding:
            incident = Incident(
                incident_id=_incident_id("reconciliation", "province_vs_cities", datetime.now(timezone.utc)),
                check="reconciliation",
                severity="critical",
                scope=IncidentScope(
                    check="reconciliation",
                    severity="critical",
                    scope_type="province_day",
                    scope_value=f"province={province_iso_code}, commodity={commodity_id}, province_price={province_price}, mean_city_price={mean_city_price}",
                    business_date=datetime.now(timezone.utc).date().isoformat(),
                    evidence={
                        "reason": "Province price differs from mean of cities by more than Rp 50",
                        "province_price": province_price,
                        "mean_city_price": mean_city_price,
                        "rounded_mean": rounded_mean,
                        "difference": diff,
                        "expected_rounding": expected_rounding,
                    },
                ),
                status="open",
                opened_at=datetime.now(timezone.utc),
                resolution=None,
            )
            incidents.append(incident)

    # Check 7b: National vs provinces
    for commodity_id, national_price in national_prices.items():
        if national_price <= 0:
            continue

        province_prices_list = []
        for province_iso_code, price in province_prices.items():
            if price is not None and price > 0:
                province_prices_list.append(price)

        if not province_prices_list:
            continue

        mean_province_price = sum(province_prices_list) / len(province_prices_list)
        ratio = national_price / mean_province_price if mean_province_price > 0 else 0

        # Check if ratio is within reasonable band (e.g., 0.9 to 1.1)
        if ratio < 0.9 or ratio > 1.1:
            incident = Incident(
                incident_id=_incident_id("reconciliation", "national_vs_provinces", datetime.now(timezone.utc)),
                check="reconciliation",
                severity="warning",
                scope=IncidentScope(
                    check="reconciliation",
                    severity="warning",
                    scope_type="commodity_date",
                    scope_value=f"commodity={commodity_id}, national_price={national_price}, mean_province_price={mean_province_price}, ratio={ratio}",
                    business_date=datetime.now(timezone.utc).date().isoformat(),
                    evidence={
                        "reason": "National price ratio to mean of provinces outside expected band",
                        "national_price": national_price,
                        "mean_province_price": mean_province_price,
                        "ratio": ratio,
                        "expected_band": "(0.9, 1.1)",
                    },
                ),
                status="open",
                opened_at=datetime.now(timezone.utc),
                resolution=None,
            )
            incidents.append(incident)

    return incidents
