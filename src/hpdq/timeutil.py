"""Time helpers. All stored timestamps are UTC; business dates are WIB calendar dates.

WIB is modelled as a fixed UTC+7 offset (ADR-009): Indonesia has no daylight saving time, and a
fixed offset avoids needing the ``tzdata`` package for ``zoneinfo`` on Windows.
"""

from datetime import UTC, date, datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7), "WIB")


def now_utc() -> datetime:
    return datetime.now(UTC)


def require_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"naive datetime not allowed: {dt!r}")
    return dt


def wib_date(dt: datetime) -> date:
    """The WIB calendar date of an aware datetime."""
    return require_aware(dt).astimezone(WIB).date()


def iso_utc(dt: datetime) -> str:
    """ISO-8601 in UTC with a ``Z`` suffix and second precision, e.g. 2026-11-12T07:21:03Z."""
    return require_aware(dt).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact_utc(dt: datetime) -> str:
    """Filename-safe UTC stamp that sorts chronologically, e.g. 20261112T072103Z."""
    return require_aware(dt).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_compact_utc(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
