"""Tests for GitHub Issue API integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hpdq.checks.github import GitHubIssue, GitHubIssueManager, github_issue_manager


@pytest.fixture
def mock_manager():
    """Create a mock GitHubIssueManager."""
    manager = GitHubIssueManager(repo="test/repo")
    manager._client = AsyncMock()
    manager._client.headers = manager.headers
    return manager


def test_github_issue_dataclass():
    """Test GitHubIssue dataclass."""
    issue = GitHubIssue(
        number=123,
        title="Test Issue",
        state="open",
        comments=0,
        labels=["bug", "priority"],
        created_at="2026-11-12T10:00:00Z",
        updated_at="2026-11-12T10:00:00Z",
    )
    
    assert issue.number == 123
    assert issue.title == "Test Issue"
    assert issue.state == "open"
    assert len(issue.labels) == 2


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_open_issue(mock_client):
    """Test opening a GitHub issue."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 456}
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    issue_number = await manager.open_issue(
        title="Test Issue",
        body="Test body",
        labels=["bug"],
    )
    
    assert issue_number == 456
    
    # Verify that request was called
    assert mock_client.call_count == 1


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_open_issue_with_labels(mock_client):
    """Test opening an issue with labels."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 789}
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    issue_number = await manager.open_issue(
        title="Test Issue",
        body="Test body",
        labels=["bug", "priority", "data-quality"],
    )
    
    assert issue_number == 789
    
    # Verify that request was called
    assert mock_client.call_count == 1


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_comment_issue(mock_client):
    """Test commenting on an issue."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 201
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    await manager.comment_issue(123, "This is a comment")
    
    # Verify that request was called
    assert mock_client.call_count == 1


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_close_issue(mock_client):
    """Test closing an issue."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    await manager.close_issue(123, "Resolved by automated check")
    
    # Verify that request was called
    assert mock_client.call_count == 1


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_add_label(mock_client):
    """Test adding a label to an issue."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    await manager.add_label(123, "bug")
    
    # Verify that request was called
    assert mock_client.call_count == 1


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_get_issue(mock_client):
    """Test getting an issue by number."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "number": 123,
        "title": "Test Issue",
        "state": "open",
        "comments": 0,
        "labels": ["bug"],
        "created_at": "2026-11-12T10:00:00Z",
        "updated_at": "2026-11-12T10:00:00Z",
    }
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    issue = await manager.get_issue(123)
    
    assert issue is not None
    assert issue.number == 123
    assert issue.state == "open"


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_get_issue_not_found(mock_client):
    """Test getting a non-existent issue."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    issue = await manager.get_issue(9999)
    
    assert issue is None


@patch("hpdq.checks.github.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_close_all(mock_client):
    """Test closing all open issues."""
    manager = GitHubIssueManager(repo="test/repo")
    
    # Configure mock client
    mock_client_instance = mock_client.return_value
    
    # Create mock response (not async, just a regular mock)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "number": 123,
            "state": "open",
            "title": "Issue 1",
            "updated_at": "2026-11-12T10:00:00Z",
        },
        {
            "number": 456,
            "state": "open",
            "title": "Issue 2",
            "updated_at": "2026-11-12T10:00:00Z",
        },
    ]
    
    # Create a coroutine that returns the mock_response
    async def mock_request(*args, **kwargs):
        return mock_response
    
    mock_client_instance.request = mock_request
    
    # Mock close_issue
    manager.close_issue = AsyncMock()
    
    await manager.close_all()
    
    # Should have called close_issue twice
    assert manager.close_issue.call_count == 2


@pytest.mark.asyncio
async def test_github_issue_manager():
    """Test github_issue_manager factory function."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
        manager = await github_issue_manager()
        assert manager is not None
        assert manager.token == "test-token"


def test_github_issue_manager_no_token():
    """Test GitHubIssueManager without token."""
    manager = GitHubIssueManager(repo="test/repo")
    assert "Authorization" not in manager.headers