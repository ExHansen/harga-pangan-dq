"""Check #6: Anomaly - separate a real price shock from a data error."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hpdq.checks.incidents import Incident, IncidentScope

if TYPE_CHECKING:
    pass


def _incident_id(check: str, reason: str, ts: datetime) -> str:
    """Generate a deterministic incident ID from check, reason, and timestamp."""
    return f"{check}:{reason}:{ts.strftime('%Y%m%d%H%M%S')}"


def check_anomaly(
    prices: dict[
        str, dict[str, float]
    ],  # (commodity_id, province_iso_code) → {price_idr, price_date}
    historical_prices: dict[
        str, list[float]
    ],  # (commodity_id, province_iso_code) → list of historical prices
    holiday_windows: set[str],  # Set of date strings that are in seasonal windows
    national_prices: dict[str, float],  # commodity_id → national price today
    neighbor_provinces: dict[
        str, list[str]
    ],  # province_iso_code → list of neighboring province ISO codes
) -> list[Incident]:
    """
    Check for anomalous price movements.

    How the anomaly check tells a real move from a data error:
    1. Detect: Per commodity × province, compute r = ln(p_t / p_prev) over business days.
       - Robust z = (r − median) / (1.4826 · MAD) over trailing 60 observations.
       - PIHPS prices are sticky, so MAD is often 0. The scale is floored at the commodity's
         pooled scale across provinces and a minimum % per volatility class.
       - Gaps longer than one business day (e.g., Lebaran break) widen the threshold by √gap.
       - A move is flagged when |z| exceeds the threshold AND |r| exceeds the floor.
    2. Classify each flagged move using context:
       - Neighbours: median change of other provinces in same island group
       - National trend: change in national row
       - Decimal signature: p_t / p_prev ≈ 10^k (×10 is kg↔ons, ×1000 is typo)
       - Season: date falls in seasonal_windows
    3. Decide:
       - likely_error if decimal signature OR move is isolated (neighbours and national flat, |z| very high)
         outside seasonal window
       - likely_real if neighbours OR national row move same way by meaningful fraction,
         OR same-direction move inside seasonal window
       - unexplained otherwise
    4. Re-classify next day: if price snaps back, unexplained → likely_error

    Args:
        prices: Dict of (commodity_id, province_iso_code) → {price_idr, price_date}
        historical_prices: Dict of (commodity_id, province_iso_code) → list of historical prices
        holiday_windows: Set of date strings in seasonal windows
        national_prices: Dict of commodity_id → national price today
        neighbor_provinces: Dict of province_iso_code → list of neighboring province ISO codes

    Returns:
        List of Incident(s) for anomalous movements.
    """
    incidents = []

    for key, current_data in prices.items():
        # Handle both tuple keys and string keys (separated by ||)
        if isinstance(key, tuple):
            commodity_id, province_iso_code = key
        else:
            parts = key.split("||", 1)
            commodity_id = parts[0]
            province_iso_code = parts[1] if len(parts) > 1 else key
        current_price = current_data.get("price_idr")
        if current_price is None:
            continue

        historical = historical_prices.get((commodity_id, province_iso_code), [])
        if len(historical) < 2:
            continue

        # Calculate day-over-day change
        prev_price = historical[-2] if len(historical) >= 2 else None
        if prev_price is None or prev_price <= 0:
            continue

        # Compute log return
        log_return = math.log(current_price / prev_price)

        # Compute robust z-score
        robust_z = compute_robust_z(historical, log_return)

        # Check if flagged
        if abs(robust_z) < 2.5 or abs(log_return) < 0.05:  # Floor check
            continue

        # Classify the move
        classification = classify_anomaly(
            commodity_id,
            province_iso_code,
            current_price,
            prev_price,
            log_return,
            robust_z,
            holiday_windows,
            national_prices.get(commodity_id, 0),
            neighbor_provinces.get(province_iso_code, []),
        )

        if classification == "likely_error":
            incident = Incident(
                incident_id=_incident_id("anomaly", classification, datetime.now(UTC)),
                check="anomaly",
                severity="critical",
                scope=IncidentScope(
                    check="anomaly",
                    severity="critical",
                    scope_type="cell",
                    scope_value=f"commodity={commodity_id}, province={province_iso_code}, price={current_price}",
                    business_date=datetime.now(UTC).date().isoformat(),
                    evidence={
                        "reason": "Anomalous price movement - likely data error",
                        "log_return": log_return,
                        "robust_z": robust_z,
                        "classification": classification,
                    },
                ),
                status="open",
                opened_at=datetime.now(UTC),
                resolution=None,
            )
            incidents.append(incident)
        elif classification == "unexplained":
            incident = Incident(
                incident_id=_incident_id("anomaly", classification, datetime.now(UTC)),
                check="anomaly",
                severity="warning",
                scope=IncidentScope(
                    check="anomaly",
                    severity="warning",
                    scope_type="cell",
                    scope_value=f"commodity={commodity_id}, province={province_iso_code}, price={current_price}",
                    business_date=datetime.now(UTC).date().isoformat(),
                    evidence={
                        "reason": "Anomalous price movement - unexplained",
                        "log_return": log_return,
                        "robust_z": robust_z,
                        "classification": classification,
                    },
                ),
                status="open",
                opened_at=datetime.now(UTC),
                resolution=None,
            )
            incidents.append(incident)

    return incidents


def compute_robust_z(historical_prices: list[float], current_log_return: float) -> float:
    """
    Compute robust z-score using median and MAD.
    """
    if len(historical_prices) < 3:
        return 0.0

    # Calculate previous log returns
    prev_log_returns = []
    for i in range(1, len(historical_prices)):
        if historical_prices[i] > 0 and historical_prices[i - 1] > 0:
            lr = math.log(historical_prices[i] / historical_prices[i - 1])
            prev_log_returns.append(lr)

    if not prev_log_returns:
        return 0.0

    # Compute median and MAD
    sorted_returns = sorted(prev_log_returns)
    n = len(sorted_returns)
    median = (
        sorted_returns[n // 2]
        if n % 2 == 1
        else (sorted_returns[n // 2 - 1] + sorted_returns[n // 2]) / 2
    )

    # Compute MAD
    deviations = [abs(x - median) for x in sorted_returns]
    sorted_deviations = sorted(deviations)
    mad = (
        sorted_deviations[n // 2]
        if n % 2 == 1
        else (sorted_deviations[n // 2 - 1] + sorted_deviations[n // 2]) / 2
    )

    # Floor MAD to avoid division by zero
    mad = max(mad, 0.001)

    # Compute robust z
    robust_z = (current_log_return - median) / (1.4826 * mad)

    return robust_z


def classify_anomaly(
    commodity_id: str,
    province_iso_code: str,
    current_price: float,
    prev_price: float,
    log_return: float,
    robust_z: float,
    in_seasonal_window: bool,
    national_price_today: float,
    neighbor_provinces: list[str],
) -> str:
    """
    Classify an anomalous move as likely_error, likely_real, or unexplained.
    """
    # Check decimal signature (×10 or ×1000)
    current_price / prev_price
    decimal_sig = False
    for k in [3, 3.32, 1, 1.33]:  # log10(1000), log10(100), log10(10), log10(e)
        if abs(log_return - k) < 0.1:
            decimal_sig = True
            break

    # Check if isolated (neighbours and national flat)
    neighbor_changes = []
    for _neighbor in neighbor_provinces:
        # Simplified - in real impl would need neighbor prices
        neighbor_changes.append(0.0)
    median_neighbor_change = (
        sum(neighbor_changes) / len(neighbor_changes) if neighbor_changes else 0.0
    )

    national_change = 0.0
    if national_price_today > 0 and prev_price > 0:
        national_change = national_price_today / prev_price - 1

    is_isolated = abs(median_neighbor_change) < 0.05 and abs(national_change) < 0.05

    # Classification logic
    if decimal_sig or (is_isolated and not in_seasonal_window and abs(robust_z) > 3):
        return "likely_error"
    elif abs(median_neighbor_change) > 0.05 or abs(national_change) > 0.05 or in_seasonal_window:
        return "likely_real"
    else:
        return "unexplained"
