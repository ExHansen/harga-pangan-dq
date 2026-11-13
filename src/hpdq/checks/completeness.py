"""Check #2: Completeness - every expected commodity × province combination is reported."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentScope

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_completeness(
    expected_combinations: set[tuple[str, str]],  # (commodity_id, province_iso_code)
    reported_combinations: set[
        tuple[str, str]
    ],  # (commodity_id, province_iso_code) that reported today
    historical_reporting: dict[
        tuple[str, str], int
    ],  # (commodity, province) → count of days reported in last 40 days
    min_reporting_threshold: float = 0.8,
) -> list[Incident]:
    """
    Check completeness of today's data.

    Rule:
    Expected set = (commodity, province) combinations that reported on ≥80% of the last 40 business days.
    This is learned, because only 27/34 provinces report some commodities.

    Severity:
    - Warning: normal gaps (some provinces don't report all commodities)
    - Critical: if a whole province is missing or completeness is <80% after 17:00 WIB

    Args:
        expected_combinations: Set of (commodity_id, province_iso_code) that should exist.
        reported_combinations: Set of (commodity_id, province_iso_code) that reported today.
        historical_reporting: Dict mapping (commodity, province) to count of days reported in last 40 days.
        min_reporting_threshold: Minimum reporting threshold (default 0.8 = 80%).

    Returns:
        List of Incident(s) if completeness is violated.
    """
    incidents = []

    # Calculate completeness percentage
    if expected_combinations:
        completeness = len(reported_combinations) / len(expected_combinations)
    else:
        completeness = 1.0

    # Check if whole province is missing
    missing_provinces = set()
    for commodity, province in expected_combinations:
        if (commodity, province) not in reported_combinations:
            missing_provinces.add(province)

    # Check critical: whole province missing
    if missing_provinces:
        incident = Incident(
            incident_id=_incident_id("completeness", "missing_province", datetime.now(UTC)),
            check="completeness",
            severity="critical",
            scope=IncidentScope(
                check="completeness",
                severity="critical",
                scope_type="province",
                scope_value=", ".join(sorted(missing_provinces)),
                business_date=datetime.now(UTC).date().isoformat(),
                evidence={
                    "reason": "One or more provinces are completely missing",
                    "missing_provinces": list(missing_provinces),
                    "reported_combinations": len(reported_combinations),
                    "expected_combinations": len(expected_combinations),
                },
            ),
            status="open",
            opened_at=datetime.now(UTC),
            resolution=None,
        )
        incidents.append(incident)

    # Check warning: completeness below threshold (after 17:00 WIB becomes critical)
    current_time = datetime.now(UTC)
    is_critical_time = current_time.hour >= 17

    if completeness < min_reporting_threshold:
        severity = "critical" if is_critical_time else "warning"
        incident = Incident(
            incident_id=_incident_id("completeness", "low_completeness", datetime.now(UTC)),
            check="completeness",
            severity=severity,
            scope=IncidentScope(
                check="completeness",
                severity=severity,
                scope_type="commodity_date",
                scope_value=f"completeness={completeness:.2%}",
                business_date=datetime.now(UTC).date().isoformat(),
                evidence={
                    "reason": "Completeness below threshold",
                    "completeness": completeness,
                    "threshold": min_reporting_threshold,
                    "reported_combinations": len(reported_combinations),
                    "expected_combinations": len(expected_combinations),
                    "is_critical_time": is_critical_time,
                },
            ),
            status="open",
            opened_at=datetime.now(UTC),
            resolution=None,
        )
        incidents.append(incident)

    return incidents
