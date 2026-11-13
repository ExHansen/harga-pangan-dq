"""Main entry point for data quality checks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hpdq.checks.incidents import Incident
    from hpdq.checks.incidents_store import IncidentStore

from hpdq.checks.anomaly import check_anomaly
from hpdq.checks.completeness import check_completeness
from hpdq.checks.duplicates import check_duplicates
from hpdq.checks.freshness import check_freshness
from hpdq.checks.incidents_store import IncidentStore
from hpdq.checks.reconciliation import check_reconciliation
from hpdq.checks.schema_drift import check_schema_drift
from hpdq.checks.validity import check_validity
from hpdq.checks.github import GitHubIssueManager


class CheckResult:
    """Result of running all checks."""

    def __init__(self, business_date: str):
        self.business_date = business_date
        self.incidents: list[Incident] = []
        self.checks_run: list[str] = []
        self.checks_passed: list[str] = []
        self.checks_failed: list[str] = []
        self.github_issue_manager: GitHubIssueManager | None = None

    def add_incident(self, incident: Incident) -> None:
        """Add an incident."""
        self.incidents.append(incident)

    def record_check(self, check_name: str, passed: bool) -> None:
        """Record whether a check passed."""
        self.checks_run.append(check_name)
        if passed:
            self.checks_passed.append(check_name)
        else:
            self.checks_failed.append(check_name)


async def run_all_checks(
    business_date: str,
    prices: dict[str, dict[str, Any]],
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
) -> CheckResult:
    """
    Run all data quality checks.

    This is the main entry point for the checks pipeline.

    Args:
        business_date: The business date (YYYY-MM-DD)
        prices: Dict of (commodity_id, province_iso_code) → price info
        snapshots: List of snapshot metadata
        expected_fingerprints: Dict of request_key → expected fingerprint
        expected_combinations: Set of expected (commodity, province) combinations
        reported_combinations: Set of reported (commodity, province) combinations
        historical_reporting: Dict mapping (commodity, province) to count
        plausible_ranges: Dict of commodity_id → (min, max) price range
        expected_units: Dict of commodity_id → expected unit
        reported_units: Dict of commodity_id → reported unit
        historical_prices: Dict of (commodity, province) → list of historical prices
        volatile_commodities: List of volatile commodity IDs
        latest_national_snapshot: Timestamp of latest national snapshot
        latest_volatile_snapshots: Dict of volatile commodity → latest snapshot
        previous_prices: Dict of (commodity, province) → previous day's price
        current_volatile_prices: Dict of volatile commodity, province → current price
        province_prices: Dict of province_iso_code → price
        city_prices: Dict of province_iso_code → list of city prices
        national_prices: Dict of commodity_id → national price
        neighbor_provinces: Dict of province_iso_code → list of neighbors
        holiday_windows: Set of dates in seasonal windows
        build_dir: Build directory for incident store

    Returns:
        CheckResult with all incidents and status.
    """
    result = CheckResult(business_date)
    store = IncidentStore(build_dir)

    # Run each check
    # Check 1: Freshness
    incidents = check_freshness(
        expected_publication_time=datetime.now(timezone.utc),
        cutoff_time=datetime(17, 0, 0, tzinfo=timezone.utc),
        latest_national_snapshot=latest_national_snapshot,
        volatile_commodities=volatile_commodities,
        latest_volatile_snapshots=latest_volatile_snapshots,
        previous_prices=previous_prices,
        current_volatile_prices=current_volatile_prices,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("freshness", False)
    if not incidents:
        result.record_check("freshness", True)

    # Check 2: Completeness
    incidents = check_completeness(
        expected_combinations=expected_combinations,
        reported_combinations=reported_combinations,
        historical_reporting=historical_reporting,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("completeness", False)
    if not incidents:
        result.record_check("completeness", True)

    # Check 3: Validity
    incidents = check_validity(
        prices=prices,
        plausible_ranges=plausible_ranges,
        expected_units=expected_units,
        reported_units=reported_units,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("validity", False)
    if not incidents:
        result.record_check("validity", True)

    # Check 4: Duplicates
    # Extract price rows from prices dict
    price_rows = []
    for (commodity_id, province_iso_code), price_info in prices.items():
        price_rows.append({
            "snapshot_id": "test",
            "commodity_id": commodity_id,
            "area_key": province_iso_code,
            "price_date": business_date,
            "price_idr": price_info.get("price_idr"),
        })
    incidents = check_duplicates(prices=price_rows)
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("duplicates", False)
    if not incidents:
        result.record_check("duplicates", True)

    # Check 5: Schema drift
    incidents = check_schema_drift(
        snapshots=snapshots,
        expected_fingerprints=expected_fingerprints,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("schema_drift", False)
    if not incidents:
        result.record_check("schema_drift", True)

    # Check 6: Anomaly
    incidents = check_anomaly(
        prices=prices,
        historical_prices=historical_prices,
        holiday_windows=holiday_windows,
        national_prices=national_prices,
        neighbor_provinces=neighbor_provinces,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("anomaly", False)
    if not incidents:
        result.record_check("anomaly", True)

    # Check 7: Reconciliation
    incidents = check_reconciliation(
        province_prices=province_prices,
        city_prices=city_prices,
        national_prices=national_prices,
    )
    for incident in incidents:
        result.add_incident(incident)
        result.record_check("reconciliation", False)
    if not incidents:
        result.record_check("reconciliation", True)

    # Log all incidents to store
    for incident in result.incidents:
        event = incident.to_dict()
        event["run_id"] = "test-run"
        store.log_event(event)

    # Initialize GitHub Issue manager
    result.github_issue_manager = await github_issue_manager()

    return result
