from datetime import date, timedelta

import httpx
import pytest

from hpdq import config
from hpdq.pihps.client import FetchFailedError, RequestBudgetExceededError, SourceRefusedError
from hpdq.pihps.specs import commodity_grid
from support import START, FakeTime, MockPihps, fixture_bytes, grid_fixture_name

D = date(2026, 11, 11)
SPEC = commodity_grid("com_13", D - timedelta(days=7), D)


def status(code: int) -> httpx.Response:
    return httpx.Response(code)


def test_success_returns_exact_body_and_identifies_the_project(
    mock_pihps: MockPihps, fake_time: FakeTime
) -> None:
    with mock_pihps.client(fake_time) as client:
        result = client.fetch(SPEC)

    assert result.body == fixture_bytes(grid_fixture_name("com_13"))
    assert result.attempts == 1
    request = mock_pihps.calls[0]
    assert request.headers["user-agent"] == config.user_agent()
    assert config.PROJECT_URL in request.headers["user-agent"]
    assert request.url.params["comcat_id"] == "com_13"


def test_requests_are_spaced_at_least_three_seconds(
    mock_pihps: MockPihps, fake_time: FakeTime
) -> None:
    with mock_pihps.client(fake_time) as client:
        results = [client.fetch(SPEC) for _ in range(3)]

    assert fake_time.sleeps == [3.0, 3.0]
    # fetched_at is the real start of each request (after the throttle wait)
    assert [r.fetched_at for r in results] == [
        START,
        START + timedelta(seconds=3),
        START + timedelta(seconds=6),
    ]


def test_no_extra_wait_when_the_response_itself_took_long(fake_time: FakeTime) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        fake_time.advance(4.0)
        return httpx.Response(200, content=b'{"data": []}')

    mock = MockPihps(overrides={"com_13": slow})
    with mock.client(fake_time) as client:
        client.fetch(SPEC)
        client.fetch(SPEC)

    assert fake_time.sleeps == []


def test_retries_5xx_with_backoff_then_succeeds(fake_time: FakeTime) -> None:
    answers = iter([status(500), status(503), httpx.Response(200, content=b'{"data": []}')])
    mock = MockPihps(overrides={"com_13": lambda r: next(answers)})
    with mock.client(fake_time) as client:
        result = client.fetch(SPEC)

    assert result.attempts == 3
    assert fake_time.sleeps == [5.0, 15.0]
    assert len(mock.calls) == 3


def test_retries_transport_errors_then_gives_up(fake_time: FakeTime) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    mock = MockPihps(overrides={"com_13": timeout})
    with mock.client(fake_time) as client, pytest.raises(FetchFailedError) as info:
        client.fetch(SPEC)

    assert info.value.attempts == 4
    assert info.value.status_code is None
    assert fake_time.sleeps == [5.0, 15.0, 45.0]


@pytest.mark.parametrize("code", [403, 429])
def test_refusal_stops_immediately_without_retry(code: int, fake_time: FakeTime) -> None:
    mock = MockPihps(overrides={"com_13": lambda r: status(code)})
    with mock.client(fake_time) as client, pytest.raises(SourceRefusedError):
        client.fetch(SPEC)

    assert len(mock.calls) == 1
    assert fake_time.sleeps == []


@pytest.mark.parametrize("code", [302, 400, 404])
def test_other_non_200_fail_without_retry(code: int, fake_time: FakeTime) -> None:
    mock = MockPihps(overrides={"com_13": lambda r: status(code)})
    with mock.client(fake_time) as client, pytest.raises(FetchFailedError) as info:
        client.fetch(SPEC)

    assert info.value.status_code == code
    assert len(mock.calls) == 1


def test_request_cap_counts_retries_and_stops_the_run(fake_time: FakeTime) -> None:
    mock = MockPihps(overrides={"com_13": lambda r: status(500)})
    with mock.client(fake_time, max_requests=2) as client:
        with pytest.raises(RequestBudgetExceededError):
            client.fetch(SPEC)
        assert client.requests_made == 2

    assert len(mock.calls) == 2
