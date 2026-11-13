"""GitHub Issue API integration for critical incidents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from hpdq.config import PROJECT_URL


@dataclass
class GitHubIssue:
    """Represents a GitHub Issue."""

    number: int
    title: str
    state: str
    comments: int
    labels: list[str]
    created_at: str
    updated_at: str


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
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self.headers, timeout=10.0)
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.request(method, f"{self.base_url}/{path}", **kwargs)

    async def open_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> int:
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

    async def get_issue(self, issue_number: int) -> GitHubIssue | None:
        """Get an issue by number."""
        url = f"repos/{self.repo}/issues/{issue_number}"
        resp = await self._request("GET", url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            state=data["state"],
            comments=data["comments"],
            labels=data.get("labels", []),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    async def close_all(self) -> None:
        """Close all open issues for this repo."""
        url = f"repos/{self.repo}/issues?state=open"
        resp = await self._request("GET", url)
        resp.raise_for_status()
        issues = resp.json()
        for issue in issues:
            await self.close_issue(
                issue["number"],
                f"Resolved by automated check. See: {PROJECT_URL}",
            )

    async def __aenter__(self) -> GitHubIssueManager:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit - close the client."""
        await self.client.aclose()


async def github_issue_manager() -> GitHubIssueManager:
    """Get GitHubIssueManager with GITHUB_TOKEN from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    return GitHubIssueManager(token=token)
