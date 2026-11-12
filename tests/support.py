"""Test helpers: a fake clock and a mock PIHPS server backed by recorded fixtures."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from hpdq.pihps.client import FetchResult, PihpsClient
from hpdq.pihps.specs import RequestSpec


class NetworkAccessError(RuntimeError):
    pass


def block_network(*args: Any, **kwargs: Any) -> Any:
    raise NetworkAccessError("network access is disabled in tests; use recorded fixtures")


FIXTURES = Path(__file__).parent / "fixtures" / "pihps"
GRID_WINDOW = "20261104-20261111"
CHILLIES = ("com_13", "com_14", "com_15", "com_16")
START = datetime(2026, 11, 12, 7, 20, 0, tzinfo=UTC)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def grid_fixture_name(comcat_id: str) -> str:
    return f"grid_{comcat_id}_{GRID_WINDOW}_k1.json"


def fixture_json(name: str) -> Any:
    return json.loads(fixture_bytes(name))


@dataclass
class FakeTime:
    """Deterministic time: ``sleep`` advances the clock instead of waiting."""

    start: datetime = START
    now_s: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now_s

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now_s += seconds

    def advance(self, seconds: float) -> None:
        self.now_s += seconds

    def clock(self) -> datetime:
        return self.start + timedelta(seconds=self.now_s)


Handler = Callable[[httpx.Request], httpx.Response]


def fixture_response(request: httpx.Request) -> httpx.Response:
    """Answer like PIHPS would, from the recorded fixtures."""
    endpoint = request.url.path.rsplit("/", 1)[-1]
    if endpoint == "GetRefCommodityAndCategory":
        body = fixture_bytes("ref_commodities.json")
    elif endpoint == "GetRefProvince":
        body = fixture_bytes("ref_provinces.json")
    elif endpoint == "GetGridDataKomoditas":
        body = fixture_bytes(grid_fixture_name(request.url.params["comcat_id"]))
    else:
        return httpx.Response(404)
    return httpx.Response(
        200, content=body, headers={"content-type": "application/json; charset=utf-8"}
    )


@dataclass
class MockPihps:
    """Records every request; ``overrides`` maps comcat_id/endpoint -> custom handler."""

    overrides: dict[str, Handler] = field(default_factory=dict)
    calls: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        target = request.url.params.get("comcat_id") or endpoint
        handler = self.overrides.get(target, fixture_response)
        return handler(request)

    def client(self, time: FakeTime, **kwargs: Any) -> PihpsClient:
        return PihpsClient.create(
            transport=httpx.MockTransport(self),
            sleep=time.sleep,
            monotonic=time.monotonic,
            clock=time.clock,
            **kwargs,
        )


def make_result(spec: RequestSpec, body: bytes, fetched_at: datetime = START) -> FetchResult:
    return FetchResult(
        spec=spec,
        status_code=200,
        body=body,
        content_type="application/json; charset=utf-8",
        fetched_at=fetched_at,
        elapsed_s=0.1,
        attempts=1,
        user_agent="test",
    )
