"""Check #5: Schema drift - the response fingerprint matches the versioned contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentScope

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_schema_drift(
    snapshots: list[dict],  # List of snapshot metadata with fingerprint
    expected_fingerprints: dict[str, str],  # request_key → expected fingerprint
) -> list[Incident]:
    """
    Check for schema drift in responses.

    Rule:
    The response fingerprint matches the versioned contract in the repo:
    - Top-level keys
    - Row keys
    - Date-key format
    - level values
    - Number format
    - The commodity id/name/unit list
    - The province name list

    Severity:
    Critical: the parser refuses unknown shapes for that endpoint and run

    Args:
        snapshots: List of snapshot metadata with fingerprint
        expected_fingerprints: Dict of request_key → expected fingerprint

    Returns:
        List of Incident(s) for schema drift.
    """
    incidents = []

    for snapshot in snapshots:
        snapshot_id = snapshot.get("snapshot_id", "")
        fingerprint = snapshot.get("fingerprint", "")
        request_key = snapshot.get("request_key", "")

        expected_fp = expected_fingerprints.get(request_key)

        if expected_fp is None:
            # Unknown request key - might be new endpoint
            incident = Incident(
                incident_id=_incident_id("schema_drift", "unknown_endpoint", datetime.now(UTC)),
                check="schema_drift",
                severity="critical",
                scope=IncidentScope(
                    check="schema_drift",
                    severity="critical",
                    scope_type="snapshot",
                    scope_value=f"snapshot_id={snapshot_id}, request_key={request_key}",
                    business_date=datetime.now(UTC).date().isoformat(),
                    evidence={
                        "reason": "Unknown request key - possible new endpoint",
                        "snapshot_id": snapshot_id,
                        "request_key": request_key,
                    },
                ),
                status="open",
                opened_at=datetime.now(UTC),
                resolution=None,
            )
            incidents.append(incident)
            continue

        if fingerprint != expected_fp:
            incident = Incident(
                incident_id=_incident_id("schema_drift", "mismatch", datetime.now(UTC)),
                check="schema_drift",
                severity="critical",
                scope=IncidentScope(
                    check="schema_drift",
                    severity="critical",
                    scope_type="snapshot",
                    scope_value=f"snapshot_id={snapshot_id}, request_key={request_key}",
                    business_date=datetime.now(UTC).date().isoformat(),
                    evidence={
                        "reason": "Response fingerprint does not match expected",
                        "snapshot_id": snapshot_id,
                        "request_key": request_key,
                        "expected_fingerprint": expected_fp,
                        "actual_fingerprint": fingerprint,
                    },
                ),
                status="open",
                opened_at=datetime.now(UTC),
                resolution=None,
            )
            incidents.append(incident)

    return incidents
