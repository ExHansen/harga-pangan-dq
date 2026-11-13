"""Tests for incident store."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hpdq.checks.incidents import Incident, IncidentEvent, IncidentScope, IncidentStatus
from hpdq.checks.incidents_store import IncidentStore


def test_incident_store_creation(tmp_path: Path):
    """Test incident store creation."""
    store = IncidentStore(tmp_path)
    assert store.db_path.exists()


def test_incident_store_log_event(tmp_path: Path):
    """Test logging an event to the store."""
    store = IncidentStore(tmp_path)

    event = {
        "event_id": "test-event-1",
        "incident_id": "test-incident-1",
        "event_type": "opened",
        "at": datetime.now(UTC).isoformat(),
        "check": "freshness",
        "severity": "critical",
        "scope": {
            "scope_type": "commodity_date",
            "scope_value": "test-value",
            "business_date": "2026-11-12",
            "evidence": {"reason": "test"},
        },
        "status": "open",
        "resolved_at": None,
        "resolution": None,
        "false_alarm": False,
        "run_id": "test-run",
        "issue_number": None,
    }

    store.log_event(event)

    # Verify in database
    conn = sqlite3.connect(store.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incident_events WHERE event_id = ?", ("test-event-1",))
    row = cursor.fetchone()
    conn.close()

    assert row is not None


def test_incident_store_get_events_by_business_date(tmp_path: Path):
    """Test getting events by business date."""
    store = IncidentStore(tmp_path)

    # Log some events
    for idx, date in enumerate(["2026-11-12", "2026-11-13", "2026-11-12"]):
        event = {
            "event_id": f"event-{date}-{idx}",
            "incident_id": f"incident-{date}-{idx}",
            "event_type": "opened",
            "at": datetime.now(UTC).isoformat(),
            "check": "freshness",
            "severity": "critical",
            "scope": {
                "scope_type": "commodity_date",
                "scope_value": "test-value",
                "business_date": date,
                "evidence": {},
            },
            "status": "open",
            "resolved_at": None,
            "resolution": None,
            "false_alarm": False,
            "run_id": "test-run",
            "issue_number": None,
        }
        store.log_event(event)

    events = store.get_events_by_business_date("2026-11-12")
    assert len(events) == 2


def test_incident_store_get_open_incidents(tmp_path: Path):
    """Test getting open incidents."""
    store = IncidentStore(tmp_path)

    # Log some events
    for status in ["open", "resolved"]:
        event = {
            "event_id": f"event-{status}",
            "incident_id": f"incident-{status}",
            "event_type": "opened",
            "at": datetime.now(UTC).isoformat(),
            "check": "freshness",
            "severity": "critical",
            "scope": {
                "scope_type": "commodity_date",
                "scope_value": "test-value",
                "business_date": "2026-11-12",
                "evidence": {},
            },
            "status": status,
            "resolved_at": datetime.now(UTC).isoformat() if status == "resolved" else None,
            "resolution": None,
            "false_alarm": False,
            "run_id": "test-run",
            "issue_number": None,
        }
        store.log_event(event)

    incidents = store.get_open_incidents()
    assert len(incidents) == 1
    assert incidents[0]["status"] == "open"


def test_incident_store_resolve_incident(tmp_path: Path):
    """Test resolving an incident."""
    store = IncidentStore(tmp_path)

    event = {
        "event_id": "test-event",
        "incident_id": "test-incident",
        "event_type": "opened",
        "at": datetime.now(UTC).isoformat(),
        "check": "freshness",
        "severity": "critical",
        "scope": {
            "scope_type": "commodity_date",
            "scope_value": "test-value",
            "business_date": "2026-11-12",
            "evidence": {},
        },
        "status": "open",
        "resolved_at": None,
        "resolution": None,
        "false_alarm": False,
        "run_id": "test-run",
        "issue_number": None,
    }
    store.log_event(event)

    # Resolve
    result = store.resolve_incident("test-incident", "Manual resolution")
    assert result is True

    # Verify
    event = store.get_incident_by_id("test-incident")
    assert event["status"] == "resolved"
    assert event["resolution"] == "Manual resolution"


def test_incident_store_mark_false_alarm(tmp_path: Path):
    """Test marking an incident as false alarm."""
    store = IncidentStore(tmp_path)

    event = {
        "event_id": "test-event",
        "incident_id": "test-incident",
        "event_type": "opened",
        "at": datetime.now(UTC).isoformat(),
        "check": "freshness",
        "severity": "critical",
        "scope": {
            "scope_type": "commodity_date",
            "scope_value": "test-value",
            "business_date": "2026-11-12",
            "evidence": {},
        },
        "status": "open",
        "resolved_at": None,
        "resolution": None,
        "false_alarm": False,
        "run_id": "test-run",
        "issue_number": None,
    }
    store.log_event(event)

    # Mark as false alarm
    result = store.mark_false_alarm("test-incident")
    assert result is True

    # Verify
    event = store.get_incident_by_id("test-incident")
    assert event["status"] == "false_alarm_marked"
    assert event["false_alarm"] == 1  # SQLite stores boolean as integer


def test_incident_store_link_issue(tmp_path: Path):
    """Test linking a GitHub issue to an incident."""
    store = IncidentStore(tmp_path)

    event = {
        "event_id": "test-event",
        "incident_id": "test-incident",
        "event_type": "opened",
        "at": datetime.now(UTC).isoformat(),
        "check": "freshness",
        "severity": "critical",
        "scope": {
            "scope_type": "commodity_date",
            "scope_value": "test-value",
            "business_date": "2026-11-12",
            "evidence": {},
        },
        "status": "open",
        "resolved_at": None,
        "resolution": None,
        "false_alarm": False,
        "run_id": "test-run",
        "issue_number": None,
    }
    store.log_event(event)

    # Link issue
    result = store.link_issue("test-incident", 123)
    assert result is True

    # Verify
    event = store.get_incident_by_id("test-incident")
    assert event["issue_number"] == 123
    assert event["status"] == "issue_linked"


def test_incident_store_get_statistics(tmp_path: Path):
    """Test getting incident statistics."""
    store = IncidentStore(tmp_path)

    # Log some events
    for check in ["freshness", "completeness", "validity"]:
        event = {
            "event_id": f"event-{check}",
            "incident_id": f"incident-{check}",
            "event_type": "opened",
            "at": datetime.now(UTC).isoformat(),
            "check": check,
            "severity": "critical",
            "scope": {
                "scope_type": "commodity_date",
                "scope_value": "test-value",
                "business_date": "2026-11-12",
                "evidence": {},
            },
            "status": "open",
            "resolved_at": None,
            "resolution": None,
            "false_alarm": False,
            "run_id": "test-run",
            "issue_number": None,
        }
        store.log_event(event)

    stats = store.get_statistics()

    assert stats["total_events"] == 3
    assert "freshness" in stats["by_check"]
    assert "critical" in stats["by_severity"]
    assert stats["open_incidents"] == 3
    assert "by_date" in stats


def test_incident_from_events():
    """Test creating Incident from events."""
    events = [
        IncidentEvent(
            event_id="event-1",
            incident_id="incident-1",
            event_type="opened",
            at=datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
            check="freshness",
            severity="critical",
            scope=IncidentScope(
                check="freshness",
                severity="critical",
                scope_type="commodity_date",
                scope_value="test-value",
                business_date="2026-11-12",
                evidence={},
            ),
            status=IncidentStatus.OPEN,
            resolution=None,
        ),
        IncidentEvent(
            event_id="event-2",
            incident_id="incident-1",
            event_type="resolved",
            at=datetime(2026, 11, 12, 11, 0, tzinfo=UTC),
            check="freshness",
            severity="critical",
            scope=IncidentScope(
                check="freshness",
                severity="critical",
                scope_type="commodity_date",
                scope_value="test-value",
                business_date="2026-11-12",
                evidence={},
            ),
            status=IncidentStatus.RESOLVED,
            resolution="Manual resolution",
        ),
    ]

    incident = Incident.from_events(events)

    assert incident.incident_id == "incident-1"
    assert incident.status == IncidentStatus.RESOLVED
    assert incident.resolution == "Manual resolution"
    # opened_at is the time of the latest event (resolved), not the opened event
    assert incident.opened_at == datetime(2026, 11, 12, 11, 0, tzinfo=UTC)


def test_incident_store_export_json(tmp_path: Path):
    """Test exporting incidents to JSON."""
    store = IncidentStore(tmp_path)

    event = {
        "event_id": "test-event",
        "incident_id": "test-incident",
        "event_type": "opened",
        "at": datetime.now(UTC).isoformat(),
        "check": "freshness",
        "severity": "critical",
        "scope": {
            "scope_type": "commodity_date",
            "scope_value": "test-value",
            "business_date": "2026-11-12",
            "evidence": {"reason": "test"},
        },
        "status": "open",
        "resolved_at": None,
        "resolution": None,
        "false_alarm": False,
        "run_id": "test-run",
        "issue_number": None,
    }
    store.log_event(event)

    # Export to JSON
    output_file = tmp_path / "incidents.json"
    # This would be implemented in sync_incidents.py
    incidents = store.get_open_incidents()

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_incidents": len(incidents),
        "incidents": incidents,
    }

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    assert output_file.exists()
    with output_file.open(encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["total_incidents"] == 1
