"""Check #4: Duplicates - (commodity, area, date) is unique within a snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentEvent, IncidentScope

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_duplicates(
    prices: list[dict],  # List of price rows with snapshot_id, commodity_id, area_key, price_date, price_idr
) -> list[Incident]:
    """
    Check for duplicate price entries.

    Rule:
    (commodity, area, date) is unique within a snapshot

    Severity:
    - Identical duplicates: warning + dedupe
    - Conflicting duplicates: critical, quarantines the commodity-day

    Args:
        prices: List of price rows with snapshot_id, commodity_id, area_key, price_date, price_idr

    Returns:
        List of Incident(s) for duplicates.
    """
    incidents = []

    # Group by (snapshot_id, commodity_id, area_key, price_date)
    groups: dict[tuple, list[dict]] = {}
    for row in prices:
        key = (
            row.get("snapshot_id"),
            row.get("commodity_id"),
            row.get("area_key"),
            row.get("price_date"),
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    for key, rows in groups.items():
        if len(rows) > 1:
            # Check if duplicates are identical or conflicting
            price_ids = [r.get("price_idr") for r in rows]
            unique_prices = set(price_ids)

            if len(unique_prices) == 1:
                # Identical duplicates - warning
                incident = Incident(
                    incident_id=_incident_id("duplicates", "identical", datetime.now(timezone.utc)),
                    check="duplicates",
                    severity="warning",
                    scope=IncidentScope(
                        check="duplicates",
                        severity="warning",
                        scope_type="cell",
                        scope_value=f"key={key}",
                        business_date=rows[0].get("price_date", ""),
                        evidence={
                            "reason": "Identical duplicate rows found",
                            "count": len(rows),
                            "price_idr": unique_prices.pop(),
                        },
                    ),
                    status="open",
                    opened_at=datetime.now(timezone.utc),
                    resolution=None,
                )
                incidents.append(incident)
            elif len(unique_prices) > 1:
                # Conflicting duplicates - critical
                incident = Incident(
                    incident_id=_incident_id("duplicates", "conflicting", datetime.now(timezone.utc)),
                    check="duplicates",
                    severity="critical",
                    scope=IncidentScope(
                        check="duplicates",
                        severity="critical",
                        scope_type="commodity_date",
                        scope_value=f"commodity={key[1]}, area={key[2]}, date={key[3]}",
                        business_date=rows[0].get("price_date", ""),
                        evidence={
                            "reason": "Conflicting duplicate rows found",
                            "count": len(rows),
                            "price_values": list(unique_prices),
                        },
                    ),
                    status="open",
                    opened_at=datetime.now(timezone.utc),
                    resolution=None,
                )
                incidents.append(incident)

    return incidents
