"""Incident store and event log."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hpdq.config import DEFAULT_BUILD_DIR


class IncidentStore:
    """SQLite store for incident events (append-only)."""

    def __init__(self, build_dir: Path | None = None):
        self.build_dir = build_dir or DEFAULT_BUILD_DIR
        self.incidents_dir = self.build_dir / "incidents"
        self.incidents_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.incidents_dir / "incident_events.db"
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_events (
                event_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                at TEXT NOT NULL,
                check_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_value TEXT NOT NULL,
                business_date TEXT NOT NULL,
                status TEXT NOT NULL,
                resolved_at TEXT,
                resolution TEXT,
                false_alarm INTEGER DEFAULT 0,
                run_id TEXT,
                issue_number INTEGER,
                evidence TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (at, event_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_business_date ON incident_events(business_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_check_name ON incident_events(check_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_incident_id ON incident_events(incident_id)
        """)
        conn.commit()
        conn.close()

    def log_event(self, event: dict[str, Any]) -> None:
        """Log a single event to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO incident_events (
                event_id, incident_id, event_type, at, check_name, severity,
                scope_type, scope_value, business_date, status, resolved_at,
                resolution, false_alarm, run_id, issue_number, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event["event_id"],
                event["incident_id"],
                event["event_type"],
                event["at"],
                event["check"],
                event["severity"],
                event["scope"]["scope_type"],
                event["scope"]["scope_value"],
                event["scope"]["business_date"],
                event["status"],
                event.get("resolved_at"),
                event.get("resolution"),
                1 if event.get("false_alarm") else 0,
                event.get("run_id"),
                event.get("issue_number"),
                json.dumps(event["scope"].get("evidence", {})),
            ),
        )
        conn.commit()
        conn.close()

    def get_events_by_business_date(self, business_date: str) -> list[dict]:
        """Get all events for a business date."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM incident_events
            WHERE business_date = ?
            ORDER BY at DESC
        """,
            (business_date,),
        )
        rows = cursor.fetchall()
        # sqlite3.Row needs to be converted with dict() not _as_dict()
        return [dict(row) for row in rows]

    def get_open_incidents(self) -> list[dict]:
        """Get all open incidents."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT incident_id, check_name, severity, scope_type, scope_value,
                   business_date, status, resolution, false_alarm, issue_number
            FROM incident_events
            WHERE status = 'open'
            ORDER BY business_date DESC
        """)
        rows = cursor.fetchall()
        # sqlite3.Row needs to be converted with dict()
        return [dict(row) for row in rows]

    def get_incident_by_id(self, incident_id: str) -> dict | None:
        """Get the latest event for an incident."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM incident_events
            WHERE incident_id = ?
            ORDER BY at DESC
            LIMIT 1
        """,
            (incident_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            # sqlite3.Row needs to be converted with dict()
            return dict(row)
        return None

    def resolve_incident(self, incident_id: str, resolution: str | None = None) -> bool:
        """Mark an incident as resolved."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE incident_events
            SET status = 'resolved', resolved_at = ?, resolution = ?
            WHERE incident_id = ?
        """,
            (datetime.now(UTC).isoformat(), resolution, incident_id),
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def mark_false_alarm(self, incident_id: str) -> bool:
        """Mark an incident as a false alarm."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE incident_events
            SET status = 'false_alarm_marked', false_alarm = 1
            WHERE incident_id = ?
        """,
            (incident_id,),
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def link_issue(self, incident_id: str, issue_number: int) -> bool:
        """Link a GitHub issue to an incident."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE incident_events
            SET issue_number = ?, status = 'issue_linked'
            WHERE incident_id = ?
        """,
            (issue_number, incident_id),
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def get_statistics(self) -> dict[str, Any]:
        """Get incident statistics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Total events
        cursor.execute("SELECT COUNT(*) FROM incident_events")
        total_events = cursor.fetchone()[0]

        # Events by check
        cursor.execute("""
            SELECT check_name, COUNT(*) as count
            FROM incident_events
            GROUP BY check_name
            ORDER BY count DESC
        """)
        by_check = {row[0]: row[1] for row in cursor.fetchall()}

        # Events by severity
        cursor.execute("""
            SELECT severity, COUNT(*) as count
            FROM incident_events
            GROUP BY severity
            ORDER BY count DESC
        """)
        by_severity = {row[0]: row[1] for row in cursor.fetchall()}

        # Open incidents
        cursor.execute("""
            SELECT COUNT(DISTINCT incident_id) as count
            FROM incident_events
            WHERE status = 'open'
        """)
        open_count = cursor.fetchone()[0]

        # Events by business date
        cursor.execute("""
            SELECT business_date, COUNT(*) as count
            FROM incident_events
            GROUP BY business_date
            ORDER BY business_date DESC
        """)
        by_date = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "total_events": total_events,
            "by_check": by_check,
            "by_severity": by_severity,
            "open_incidents": open_count,
            "by_date": by_date,
        }


def load_events(build_dir: Path | None = None) -> IncidentStore:
    """Load or create the incident store."""
    return IncidentStore(build_dir)
