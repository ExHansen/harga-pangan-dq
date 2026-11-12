"""A deliberately polite HTTP client for PIHPS.

Rules (docs/design.md §2):
- at least ``min_interval_s`` between the starts of two requests, strictly sequential;
- retries with backoff only for timeouts, connection errors and 5xx;
- 403 or 429 means "the source does not want this": raise immediately and stop the run;
- a hard cap on HTTP attempts per client (one client per run), retries included.

Time and sleeping are injected so tests run instantly and never touch the network.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from hpdq import config
from hpdq.pihps.specs import RequestSpec
from hpdq.timeutil import now_utc

log = logging.getLogger(__name__)


class SourceRefusedError(RuntimeError):
    """The source answered 403/429. The run must stop; retrying would be impolite."""


class RequestBudgetExceededError(RuntimeError):
    """The per-run request cap was reached (protects the source from a runaway loop)."""


class FetchFailedError(RuntimeError):
    """A request failed permanently (non-retryable status, or retries exhausted)."""

    def __init__(self, message: str, *, status_code: int | None, attempts: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


@dataclass(frozen=True)
class FetchResult:
    spec: RequestSpec
    status_code: int
    body: bytes
    content_type: str | None
    fetched_at: datetime
    elapsed_s: float
    attempts: int
    user_agent: str


class PihpsClient:
    def __init__(
        self,
        http: httpx.Client,
        *,
        min_interval_s: float = config.MIN_REQUEST_INTERVAL_S,
        max_requests: int = config.MAX_REQUESTS_PER_RUN,
        backoff_s: tuple[float, ...] = config.RETRY_BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self._http = http
        self._min_interval_s = min_interval_s
        self._max_requests = max_requests
        self._backoff_s = backoff_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._clock = clock
        self._last_start: float | None = None
        self.requests_made = 0

    @classmethod
    def create(
        cls, *, transport: httpx.BaseTransport | None = None, **kwargs: Any
    ) -> "PihpsClient":
        """The production client: descriptive User-Agent, timeout, no redirects followed."""
        http = httpx.Client(
            headers={"User-Agent": config.user_agent(), "Accept": "application/json"},
            timeout=config.REQUEST_TIMEOUT_S,
            follow_redirects=False,  # a redirect (e.g. to an error page) is a failure, not data
            transport=transport,
        )
        return cls(http, **kwargs)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PihpsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self) -> None:
        if self._last_start is not None:
            wait = self._last_start + self._min_interval_s - self._monotonic()
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._monotonic()

    def _start_attempt(self, spec: RequestSpec) -> tuple[float, datetime]:
        """Enforce the cap and the interval; return the real start (monotonic, wall clock)."""
        if self.requests_made >= self._max_requests:
            raise RequestBudgetExceededError(
                f"request cap of {self._max_requests} per run reached before {spec.key}"
            )
        self._throttle()
        self.requests_made += 1
        return self._monotonic(), self._clock()

    def fetch(self, spec: RequestSpec) -> FetchResult:
        max_attempts = len(self._backoff_s) + 1
        for attempt in range(1, max_attempts + 1):
            started, fetched_at = self._start_attempt(spec)
            retry_reason: str
            try:
                response = self._http.get(spec.url, params=spec.params_dict())
            except httpx.TransportError as exc:
                retry_reason = f"{type(exc).__name__}: {exc}"
                status: int | None = None
            else:
                status = response.status_code
                if status == 200:
                    return FetchResult(
                        spec=spec,
                        status_code=status,
                        body=response.content,
                        content_type=response.headers.get("content-type"),
                        fetched_at=fetched_at,
                        elapsed_s=round(self._monotonic() - started, 3),
                        attempts=attempt,
                        user_agent=str(response.request.headers.get("user-agent", "")),
                    )
                if status in (403, 429):
                    raise SourceRefusedError(
                        f"source answered HTTP {status} for {spec.key}; stopping the run"
                    )
                if status < 500:
                    raise FetchFailedError(
                        f"HTTP {status} for {spec.key} (not retryable)",
                        status_code=status,
                        attempts=attempt,
                    )
                retry_reason = f"HTTP {status}"

            if attempt == max_attempts:
                raise FetchFailedError(
                    f"{spec.key} failed after {attempt} attempts: {retry_reason}",
                    status_code=status,
                    attempts=attempt,
                )
            delay = self._backoff_s[attempt - 1]
            log.warning("%s: %s; retrying in %.0fs", spec.key, retry_reason, delay)
            self._sleep(delay)

        raise AssertionError("unreachable")  # pragma: no cover
