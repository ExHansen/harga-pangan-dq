"""Ingestion: fetch a plan of requests politely and store every new response immutably."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from hpdq.pihps.client import (
    FetchFailedError,
    PihpsClient,
    RequestBudgetExceededError,
    SourceRefusedError,
)
from hpdq.pihps.specs import RequestSpec
from hpdq.raw.manifest import Manifest
from hpdq.raw.store import RawStore
from hpdq.timeutil import iso_utc, now_utc

log = logging.getLogger(__name__)

RunStatus = Literal["success", "partial", "failed"]


@dataclass
class IngestSummary:
    run_id: str
    business_date: date
    planned: int
    stored: int = 0
    deduped: int = 0
    failed: int = 0
    skipped: int = 0
    http_attempts: int = 0
    stop_reason: str | None = None
    manifest_path: Path | None = None
    stored_paths: list[Path] = field(default_factory=list)

    @property
    def status(self) -> RunStatus:
        ok = self.stored + self.deduped
        if ok == self.planned:
            return "success"
        return "partial" if ok > 0 else "failed"


def run_ingest(
    specs: list[RequestSpec],
    *,
    business_date: date,
    client: PihpsClient,
    store: RawStore,
    run_id: str,
    clock: Callable[[], datetime] = now_utc,
) -> IngestSummary:
    summary = IngestSummary(run_id=run_id, business_date=business_date, planned=len(specs))
    manifest = Manifest(run_id=run_id, started_at=clock())
    try:
        for i, spec in enumerate(specs):
            endpoint = spec.endpoint.value
            try:
                result = client.fetch(spec)
            except (SourceRefusedError, RequestBudgetExceededError) as exc:
                summary.failed += 1
                summary.stop_reason = str(exc)
                manifest.add(key=spec.key, endpoint=endpoint, outcome="refused", error=str(exc))
                for rest in specs[i + 1 :]:
                    summary.skipped += 1
                    manifest.add(key=rest.key, endpoint=rest.endpoint.value, outcome="skipped")
                log.error("stopping run: %s", exc)
                break
            except FetchFailedError as exc:
                summary.failed += 1
                manifest.add(
                    key=spec.key,
                    endpoint=endpoint,
                    outcome="failed",
                    status_code=exc.status_code,
                    attempts=exc.attempts,
                    error=str(exc),
                )
                log.warning("%s", exc)
                continue

            put = store.put(result, run_id=run_id)
            if put.created:
                summary.stored += 1
                summary.stored_paths.append(put.snapshot.body_path)
            else:
                summary.deduped += 1
            manifest.add(
                key=spec.key,
                endpoint=endpoint,
                outcome="stored" if put.created else "dedup",
                params=spec.params_dict(),
                status_code=result.status_code,
                attempts=result.attempts,
                bytes=len(result.body),
                sha256=put.sha256,
                fetched_at=iso_utc(result.fetched_at),
                elapsed_s=result.elapsed_s,
                snapshot=put.snapshot.body_path.relative_to(store.root).as_posix(),
            )
            log.info("%s: %s", spec.key, "stored" if put.created else "unchanged (dedup)")
    finally:
        summary.http_attempts = client.requests_made
        summary.manifest_path = manifest.write(store.root)
    return summary
