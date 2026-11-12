"""Global test configuration.

The autouse guard makes any real network connection fail loudly: tests must use recorded fixtures
through ``httpx.MockTransport`` (see ``support.py``).
"""

import socket
from collections.abc import Iterator

import pytest

from support import FakeTime, MockPihps, block_network


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(socket.socket, "connect", block_network)
    monkeypatch.setattr(socket.socket, "connect_ex", block_network)
    monkeypatch.setattr(socket, "create_connection", block_network)
    monkeypatch.setattr(socket, "getaddrinfo", block_network)
    yield


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def mock_pihps() -> MockPihps:
    return MockPihps()
