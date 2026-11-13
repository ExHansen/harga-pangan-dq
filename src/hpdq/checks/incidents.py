"""Incident model and GitHub Issue integration for data quality checks."""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx

from hpdq.config import PROJECT_URL


class IncidentStatus(Enum):
    """Incident lifecycle states."""

    OPEN = "open"
    RESOLVED = "resolved"
    FALSE_ALARM_MARKED = "false_alarm_marked"
    ISSUE_LINKED = "issue_linked"


@dataclass
class IncidentScope:
    """Scope of an incident (what data is affected)."""

    check: str
    severity: str  # "critical" or "warning"
    scope_type: str  # "cell", "commodity_day", "province_day", "commodity_date", etc.
    scope_value: str  # JSON-serializable description of the scope
    business_date: str  # Date of the data (YYYY-MM-DD)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "scope_type": self.scope_type,
            "scope_value": self.scope_value,
            "business_date": self.business_date,
            "evidence": self.evidence,
        }


@dataclass
class IncidentEvent:
    """Single event in the incident lifecycle (append-only log)."""

    event_id: str
    incident_id: str
    event_type: str  # "opened", "resolved", "false_alarm_marked", "issue_linked"
    at: datetime
    check: str
    severity: str
    scope: IncidentScope
    status: IncidentStatus
    resolved_at: datetime | None = None
    resolution: str | None = None
    false_alarm: bool = False
    run_id: str | None = None
    issue_number: int | None = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "incident_id": self.incident_id,
            "event_type": self.event_type,
            "at": self.at.isoformat(),
            "check": self.check,
            "severity": self.severity,
            "scope": self.scope.to_dict(),
            "status": self.status.value if isinstance(self.status, IncidentStatus) else self.status,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution,
            "false_alarm": self.false_alarm,
            "run_id": self.run_id,
            "issue_number": self.issue_number,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class Incident:
    """Current state of an incident (view of the latest event)."""

    incident_id: str
    check: str
    severity: str
    scope: IncidentScope
    status: IncidentStatus
    opened_at: datetime
    resolution: str | None = None
    false_alarm: bool = False
    issue_number: int | None = None

    @classmethod
    def from_events(cls, events: list[IncidentEvent]) -> "Incident":
        """Create Incident from list of events (should be latest only)."""
        latest = max(events, key=lambda e: e.at)
        return cls(
            incident_id=latest.incident_id,
            check=latest.check,
            severity=latest.severity,
            scope=latest.scope,
            status=latest.status,
            opened_at=latest.at,
            resolution=latest.resolution,
            false_alarm=latest.false_alarm,
            issue_number=latest.issue_number,
        )

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "check": self.check,
            "severity": self.severity,
            "scope": self.scope.to_dict(),
            "status": self.status.value if isinstance(self.status, IncidentStatus) else self.status,
            "opened_at": self.opened_at.isoformat(),
            "resolution": self.resolution,
            "false_alarm": self.false_alarm,
            "issue_number": self.issue_number,
        }


def _incident_id(check: str, scope: IncidentScope) -> str:
    """Generate incident_id = hash(check, scope, business_date)."""
    data = f"{check}|{scope.to_dict()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class GitHubIssueManager:
    """GitHub Issue API for critical incidents."""

    def __init__(
        self,
        repo: str = "ExHansen/harga-pangan-dq",
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ):
        self.repo = repo
        self.base_url = base_url
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers=self.headers, timeout=10.0)
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.request(method, f"{self.base_url}/{path}", **kwargs)

    async def open_issue(self, title: str, body: str, labels: list[str] | None = None) -> int:
        """Open a GitHub Issue and return the issue number."""
        url = f"repos/{self.repo}/issues"
        data = {"title": title, "body": body, "labels": labels or []}
        resp = await self._request("POST", url, json=data)
        resp.raise_for_status()
        issue_number = resp.json()["number"]
        return issue_number

    async def comment_issue(self, issue_number: int, body: str) -> None:
        """Add a comment to an issue."""
        url = f"repos/{self.repo}/issues/{issue_number}/comments"
        data = {"body": body}
        resp = await self._request("POST", url, json=data)
        resp.raise_for_status()

    async def close_issue(self, issue_number: int, comment: str | None = None) -> None:
        """Close an issue (with optional comment)."""
        url = f"repos/{self.repo}/issues/{issue_number}"
        data = {"state": "closed"}
        if comment:
            data["comments"] = [{"body": comment}]
        resp = await self._request("PATCH", url, json=data)
        resp.raise_for_status()

    async def add_label(self, issue_number: int, label: str) -> None:
        """Add a label to an issue."""
        url = f"repos/{self.repo}/issues/{issue_number}/labels"
        data = [label]
        resp = await self._request("PUT", url, json=data)
        resp.raise_for_status()

    async def close_all(self) -> None:
        """Close all open issues for this repo."""
        url = f"repos/{self.repo}/issues?state=open"
        resp = await self._request("GET", url)
        resp.raise_for_status()
        issues = resp.json()
        for issue in issues:
            await self.close_issue(
                issue["number"], f"Resolved by automated check. See: {PROJECT_URL}"
            )


async def github_issue_manager() -> GitHubIssueManager:
    """Get GitHubIssueManager with GITHUB_TOKEN from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    return GitHubIssueManager(token=token)
