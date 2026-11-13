"""Check #3: Validity - price > 0, unit as expected, within plausible range."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentEvent, IncidentScope
from hpdq.timeutil import now_utc

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_validity(
    prices: dict[str, dict[str, float | str]],  # (commodity_id, province_iso_code) → {price_raw, price_idr, is_missing}
    plausible_ranges: dict[str, tuple[int, int]],  # commodity_id → (min, max) in IDR
    expected_units: dict[str, str],  # commodity_id → expected unit (e.g., "kg")
    reported_units: dict[str, str],  # commodity_id → unit reported by source
) -> list[Incident]:
    """
    Check validity of prices.

    Rules:
    1. The price string parses to an integer > 0
    2. The price lies in the commodity's plausible range (seed, set from history with a wide margin)
    3. The ref denomination equals the expected unit

    Severity:
    - Critical: quarantines the cell (parse or range) or the commodity-day (unit)

    Args:
        prices: Dict of (commodity_id, province_iso_code) → {price_raw, price_idr, is_missing}
        plausible_ranges: Dict of commodity_id → (min, max) in IDR
        expected_units: Dict of commodity_id → expected unit (e.g., "kg")
        reported_units: Dict of commodity_id → unit reported by source

    Returns:
        List of Incident(s) for invalid prices.
    """
    incidents = []

    for key, price_info in prices.items():
        # Handle both tuple keys and string keys (separated by ||)
        if isinstance(key, tuple):
            commodity_id, province_iso_code = key
        else:
            parts = key.split("||", 1)
            commodity_id = parts[0]
            province_iso_code = parts[1] if len(parts) > 1 else key
        # Skip missing prices
        if price_info.get("is_missing"):
            continue

        price_raw = price_info.get("price_raw", "")
        price_idr = price_info.get("price_idr")

        # Check 1: Price parses to integer > 0
        if price_idr is None or not isinstance(price_idr, int) or price_idr <= 0:
            incident = Incident(
                incident_id=_incident_id("validity", "parse_error", datetime.now(timezone.utc)),
                check="validity",
                severity="critical",
                scope=IncidentScope(
                    check="validity",
                    severity="critical",
                    scope_type="cell",
                    scope_value=f"commodity={commodity_id}, province={province_iso_code}, price_raw={price_raw}",
                    business_date=datetime.now(timezone.utc).date().isoformat(),
                    evidence={
                        "reason": "Price does not parse to integer > 0",
                        "price_raw": price_raw,
                        "price_idr": price_idr,
                    },
                ),
                status="open",
                opened_at=datetime.now(timezone.utc),
                resolution=None,
            )
            incidents.append(incident)
            continue

        # Check 2: Price within plausible range
        if commodity_id in plausible_ranges:
            min_price, max_price = plausible_ranges[commodity_id]
            if price_idr < min_price or price_idr > max_price:
                incident = Incident(
                    incident_id=_incident_id("validity", "out_of_range", datetime.now(timezone.utc)),
                    check="validity",
                    severity="critical",
                    scope=IncidentScope(
                        check="validity",
                        severity="critical",
                        scope_type="cell",
                        scope_value=f"commodity={commodity_id}, province={province_iso_code}, price={price_idr}",
                        business_date=datetime.now(timezone.utc).date().isoformat(),
                        evidence={
                            "reason": "Price outside plausible range",
                            "price_idr": price_idr,
                            "plausible_min": min_price,
                            "plausible_max": max_price,
                        },
                    ),
                    status="open",
                    opened_at=datetime.now(timezone.utc),
                    resolution=None,
                )
                incidents.append(incident)
                continue

        # Check 3: Unit mismatch
        if commodity_id in expected_units and commodity_id in reported_units:
            expected_unit = expected_units[commodity_id]
            reported_unit = reported_units[commodity_id]
            if expected_unit != reported_unit:
                incident = Incident(
                    incident_id=_incident_id("validity", "unit_mismatch", datetime.now(timezone.utc)),
                    check="validity",
                    severity="critical",
                    scope=IncidentScope(
                        check="validity",
                        severity="critical",
                        scope_type="commodity_date",
                        scope_value=f"commodity={commodity_id}, expected_unit={expected_unit}, reported_unit={reported_unit}",
                        business_date=datetime.now(timezone.utc).date().isoformat(),
                        evidence={
                            "reason": "Unit mismatch between expected and reported",
                            "commodity_id": commodity_id,
                            "expected_unit": expected_unit,
                            "reported_unit": reported_unit,
                        },
                    ),
                    status="open",
                    opened_at=datetime.now(timezone.utc),
                    resolution=None,
                )
                incidents.append(incident)

    return incidents
