import socket

import httpx
import pytest

from support import NetworkAccessError


def test_raw_socket_connect_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("www.bi.go.id", 443), timeout=1)


def test_real_httpx_request_is_blocked() -> None:
    with pytest.raises((NetworkAccessError, httpx.ConnectError)):
        httpx.get("https://www.bi.go.id/robots.txt", timeout=1)
