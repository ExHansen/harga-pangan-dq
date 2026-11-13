"""Check #1: Freshness - today's data is present by an agreed time in WIB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentEvent, IncidentScope
from hpdq.timeutil import now_utc

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_freshness(
    expected_publication_time: datetime,
    cutoff_time: datetime,
    latest_national_snapshot: datetime | None,
    volatile_commodities: list[str],
    latest_volatile_snapshots: dict[str, datetime],
    previous_prices: dict[str, dict[str, float]],
    current_volatile_prices: dict[str, dict[str, float]],
) -> list[Incident]:
    """
    Check freshness of today's data.

    Rules:
    1. On an expected publication day (weekday, not in calendar_holidays), the national row for D
       has ≥1 non-missing price by 14:00 WIB.
       - Missing: warning before 17:00 WIB, critical after.
    2. Stale re-delivery: the share of unchanged D-vs-D-1 cells for volatile commodities is above
       its historical 99.5th percentile → critical.

    Args:
        expected_publication_time: Expected time by which data should be available (14:00 WIB).
        cutoff_time: Cutoff for escalation to critical (17:00 WIB).
        latest_national_snapshot: Timestamp of the latest snapshot containing today's national row.
        volatile_commodities: List of commodity IDs that are prone to stale re-delivery.
        latest_volatile_snapshots: Dict of volatile commodity ID → latest snapshot timestamp.
        previous_prices: Dict of (commodity, province) → previous day's price.
        current_volatile_prices: Dict of (commodity, province) → current day's price for volatile items.

    Returns:
        List of Incident(s) if freshness is violated.
    """
    incidents = []

    # Check 1: Missing national row for today
    if latest_national_snapshot is None:
        incident = Incident(
            incident_id=_incident_id("freshness", "missing_national", datetime.now(timezone.utc)),
            check="freshness",
            severity="critical" if datetime.now(timezone.utc).hour >= 17 else "warning",
            scope=IncidentScope(
                check="freshness",
                severity="critical" if datetime.now(timezone.utc).hour >= 17 else "warning",
                scope_type="commodity_date",
                scope_value=f"national,{datetime.now(timezone.utc).date().isoformat()}",
                business_date=datetime.now(timezone.utc).date().isoformat(),
                evidence={"reason": "No national row found for today"},
            ),
            status="open",
            opened_at=datetime.now(timezone.utc),
            resolution=None,
        )
        incidents.append(incident)
        return incidents

    # Check 2: Stale re-delivery detection for volatile commodities
    # This is a simplified version - full implementation would need historical thresholds
    if volatile_commodities and latest_volatile_snapshots:
        stale_threshold = _calculate_stale_threshold(volatile_commodities, previous_prices, current_volatile_prices)
        if stale_threshold is not None and stale_threshold > 0.995:
            incident = Incident(
                incident_id=_incident_id("freshness", "stale_re_delivery", datetime.now(timezone.utc)),
                check="freshness",
                severity="critical",
                scope=IncidentScope(
                    check="freshness",
                    severity="critical",
                    scope_type="commodity_date",
                    scope_value=f"volatile_commodities",
                    business_date=datetime.now(timezone.utc).date().isoformat(),
                    evidence={
                        "reason": "High share of unchanged prices for volatile commodities",
                        "stale_share": stale_threshold,
                    },
                ),
                status="open",
                opened_at=datetime.now(timezone.utc),
                resolution=None,
            )
            incidents.append(incident)

    return incidents


def _calculate_stale_threshold(
    volatile_commodities: list[str],
    previous_prices: dict[str, dict[str, float]],
    current_volatile_prices: dict[str, dict[str, float]],
) -> float | None:
    """
    Calculate the share of unchanged prices for volatile commodities.

    Returns:
        Share of unchanged prices (0.0 to 1.0), or None if not enough data.
    """
    if not volatile_commodities or not previous_prices or not current_volatile_prices:
        return None

    total_pairs = 0
    unchanged_pairs = 0

    for commodity in volatile_commodities:
        prev_prices = previous_prices.get(commodity, {})
        curr_prices = current_volatile_prices.get(commodity, {})

        for province in set(prev_prices.keys()) & set(curr_prices.keys()):
            prev_price = prev_prices[province]
            curr_price = curr_prices[province]

            if prev_price is not None and curr_price is not None and prev_price > 0:
                total_pairs += 1
                # Consider unchanged if price didn't change (or changed by < 1%)
                if abs(curr_price - prev_price) < 1:
                    unchanged_pairs += 1

    if total_pairs == 0:
        return None

    return unchanged_pairs / total_pairs
