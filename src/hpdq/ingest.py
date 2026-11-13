"""Ingestion: fetch a plan of requests politely and store every new response immutably, then run data quality checks."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from hpdq.checks import run_all_checks
from hpdq.checks.incidents_store import IncidentStore
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
    already_stored: int = 0
    http_attempts: int = 0
    stop_reason: str | None = None
    manifest_path: Path | None = None
    stored_paths: list[Path] = field(default_factory=list)

    @property
    def status(self) -> RunStatus:
        ok = self.stored + self.deduped + self.already_stored
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
    skip_existing: bool = False,
) -> IngestSummary:
    """Fetch ``specs`` in order and store new responses.

    ``skip_existing`` (used by backfill) does not request anything that already has a snapshot, so
    an interrupted backfill resumes where it stopped without re-asking the source.
    """
    summary = IngestSummary(run_id=run_id, business_date=business_date, planned=len(specs))
    manifest = Manifest.open(store.root, run_id=run_id, started_at=clock())
    summary.manifest_path = manifest.path
    try:
        for i, spec in enumerate(specs):
            endpoint = spec.endpoint.value
            if skip_existing:
                existing = store.latest(spec)
                if existing is not None:
                    summary.already_stored += 1
                    manifest.add(
                        key=spec.key,
                        endpoint=endpoint,
                        outcome="exists",
                        snapshot=existing.body_path.relative_to(store.root).as_posix(),
                    )
                    continue
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
    return summary


def run_checks(
    business_date: date,
    prices: dict[str, dict[str, any]],
    snapshots: list[dict],
    expected_fingerprints: dict[str, str],
    expected_combinations: set[tuple[str, str]],
    reported_combinations: set[tuple[str, str]],
    historical_reporting: dict[tuple[str, str], int],
    plausible_ranges: dict[str, tuple[int, int]],
    expected_units: dict[str, str],
    reported_units: dict[str, str],
    historical_prices: dict[str, list[float]],
    volatile_commodities: list[str],
    latest_national_snapshot: datetime | None,
    latest_volatile_snapshots: dict[str, datetime],
    previous_prices: dict[str, dict[str, float]],
    current_volatile_prices: dict[str, dict[str, float]],
    province_prices: dict[str, float],
    city_prices: dict[str, list[dict]],
    national_prices: dict[str, float],
    neighbor_provinces: dict[str, list[str]],
    holiday_windows: set[str],
    build_dir: Path | None = None,
) -> tuple[list, dict]:
    """
    Run data quality checks on ingested data.
    
    Returns:
        Tuple of (incidents, results_dict)
    """
    from hpdq.checks import (
        check_anomaly,
        check_completeness,
        check_duplicates,
        check_freshness,
        check_reconciliation,
        check_schema_drift,
        check_validity,
    )
    from hpdq.checks.github import github_issue_manager
    from hpdq.checks.incidents import Incident
    from hpdq.checks.incidents_store import IncidentStore
    
    result = {
        "business_date": business_date.isoformat(),
        "checks": [],
        "incidents": [],
    }
    
    store = IncidentStore(build_dir)
    
    # Check 1: Freshness
    log.info("Running freshness check...")
    freshness_incidents = check_freshness(
        expected_publication_time=datetime(14, 0, 0, tzinfo=datetime.now().astimezone().tzinfo),
        cutoff_time=datetime(17, 0, 0, tzinfo=datetime.now().astimezone().tzinfo),
        latest_national_snapshot=latest_national_snapshot,
        volatile_commodities=volatile_commodities,
        latest_volatile_snapshots=latest_volatile_snapshots,
        previous_prices=previous_prices,
        current_volatile_prices=current_volatile_prices,
    )
    result["checks"].append({"name": "freshness", "passed": len(freshness_incidents) == 0})
    for incident in freshness_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Freshness check critical: %s", incident.scope.scope_value)
    
    # Check 2: Completeness
    log.info("Running completeness check...")
    completeness_incidents = check_completeness(
        expected_combinations=expected_combinations,
        reported_combinations=reported_combinations,
        historical_reporting=historical_reporting,
    )
    result["checks"].append({"name": "completeness", "passed": len(completeness_incidents) == 0})
    for incident in completeness_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Completeness check critical: %s", incident.scope.scope_value)
    
    # Check 3: Validity
    log.info("Running validity check...")
    validity_incidents = check_validity(
        prices=prices,
        plausible_ranges=plausible_ranges,
        expected_units=expected_units,
        reported_units=reported_units,
    )
    result["checks"].append({"name": "validity", "passed": len(validity_incidents) == 0})
    for incident in validity_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Validity check critical: %s", incident.scope.scope_value)
    
    # Check 4: Duplicates
    log.info("Running duplicates check...")
    duplicates_incidents = check_duplicates(prices=list(prices.values()))
    result["checks"].append({"name": "duplicates", "passed": len(duplicates_incidents) == 0})
    for incident in duplicates_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Duplicates check critical: %s", incident.scope.scope_value)
    
    # Check 5: Schema drift
    log.info("Running schema drift check...")
    schema_incidents = check_schema_drift(
        snapshots=snapshots,
        expected_fingerprints=expected_fingerprints,
    )
    result["checks"].append({"name": "schema_drift", "passed": len(schema_incidents) == 0})
    for incident in schema_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Schema drift check critical: %s", incident.scope.scope_value)
    
    # Check 6: Anomaly
    log.info("Running anomaly check...")
    anomaly_incidents = check_anomaly(
        prices=prices,
        historical_prices=historical_prices,
        holiday_windows=holiday_windows,
        national_prices=national_prices,
        neighbor_provinces=neighbor_provinces,
    )
    result["checks"].append({"name": "anomaly", "passed": len(anomaly_incidents) == 0})
    for incident in anomaly_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Anomaly check critical: %s", incident.scope.scope_value)
    
    # Check 7: Reconciliation
    log.info("Running reconciliation check...")
    reconciliation_incidents = check_reconciliation(
        province_prices=province_prices,
        city_prices=city_prices,
        national_prices=national_prices,
    )
    result["checks"].append({"name": "reconciliation", "passed": len(reconciliation_incidents) == 0})
    for incident in reconciliation_incidents:
        result["incidents"].append(incident.to_dict())
        if incident.severity == "critical":
            log.warning("Reconciliation check critical: %s", incident.scope.scope_value)
    
    # Log all incidents to store
    for incident in result["incidents"]:
        incident["run_id"] = run_id
        store.log_event(incident)
    
    # Initialize GitHub Issue manager for critical incidents
    async def process_github_issues():
        github_manager = await github_issue_manager()
        critical_incidents = [i for i in result["incidents"] if i.get("severity") == "critical"]
        for incident in critical_incidents:
            try:
                issue_number = await github_manager.open_issue(
                    title=f"[{business_date.isoformat()}] {incident.get('check', 'unknown')} - {incident.get('incident_id', 'unknown')}",
                    body=_build_issue_body(incident),
                    labels=["data-quality", "data-quality/critical", f"data-quality/{incident.get('check', 'unknown')}"],
                )
                incident["issue_number"] = issue_number
                log.info("Opened GitHub Issue #%d for incident %s", issue_number, incident["incident_id"])
            except Exception as e:
                log.error("Failed to open GitHub Issue for incident %s: %s", incident["incident_id"], e)
    
    asyncio.run(process_github_issues())
    
    # Print summary
    passed = sum(1 for c in result["checks"] if c["passed"])
    failed = len(result["checks"]) - passed
    log.info("Checks: %d/%d passed, %d failed", passed, len(result["checks"]), failed)
    
    return result["incidents"], result


def _build_issue_body(incident: dict) -> str:
    """Build GitHub issue body from incident."""
    scope = incident.get("scope", {})
    evidence = incident.get("evidence", {})
    
    lines = [
        "## Incident",
        "",
        f"- **Business date:** {incident.get('business_date', 'unknown')}",
        f"- **Check:** {incident.get('check', 'unknown')}",
        f"- **Severity:** {incident.get('severity', 'unknown')}",
        f"- **Incident ID:** `{incident.get('incident_id', 'unknown')}`",
        "",
        "## Scope",
        "",
        scope.get("scope_type", "unknown"),
        f"{scope.get('scope_value', '')}",
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(evidence, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Resolution",
        "",
        "Awaiting investigation.",
        "",
        "Auto-generated by harga-pangan-dq.",
    ]
    return "\n".join(lines)
