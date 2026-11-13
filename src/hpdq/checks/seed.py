"""Seeds for calendar_holidays and seasonal_windows."""

from __future__ import annotations

from pathlib import Path

from hpdq.config import DEFAULT_SEEDS_DIR


def get_seeds_dir() -> Path:
    """Get the seeds directory."""
    return DEFAULT_SEEDS_DIR


def write_calendar_holidays(seed_dir: Path | None = None) -> None:
    """
    Write calendar_holidays seed file.

    Contains Indonesian national holidays and religious holidays.

    Format: CSV with columns:
      - date: YYYY-MM-DD
      - name: Holiday name
      - type: national|religious|local
    """
    seed_dir = seed_dir or get_seeds_dir()
    seed_dir.mkdir(parents=True, exist_ok=True)

    seed_file = seed_dir / "calendar_holidays.csv"

    holidays = [
        # New Year
        {"date": "2026-01-01", "name": "Tahun Baru Masehi", "type": "national"},
        # Chinese New Year (varies by year)
        {"date": "2026-01-29", "name": "Tahun Baru Imlek", "type": "religious"},
        # Independence Day
        {"date": "2026-08-17", "name": "Hari Kemerdekaan RI", "type": "national"},
        # Nyepi (Balinese New Year - varies)
        {"date": "2026-03-17", "name": "Nyepi", "type": "religious"},
        # Eid al-Fitr (Ramadan ends - varies)
        {"date": "2026-03-28", "name": "Idul Fitri", "type": "religious"},
        # Waisak (Buddha's Birthday - varies)
        {"date": "2026-05-22", "name": "Waisak", "type": "religious"},
        # Eid al-Adha (varies)
        {"date": "2026-07-09", "name": "Idul Adha", "type": "religious"},
        # Christmas
        {"date": "2026-12-25", "name": "Natal", "type": "religious"},
    ]

    lines = ["date,name,type"]
    for h in holidays:
        lines.append(f"{h['date']},{h['name']},{h['type']}")

    with Path(seed_file).open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"Wrote calendar_holidays seed to {seed_file}")


def write_seasonal_windows(seed_dir: Path | None = None) -> None:
    """
    Write seasonal_windows seed file.

    Contains seasonal patterns for commodity prices.

    Format: CSV with columns:
      - commodity_id: Commodity identifier
      - start_date: Start of seasonal window (YYYY-MM-DD)
      - end_date: End of seasonal window (YYYY-MM-DD)
      - volatility_multiplier: Expected volatility increase
    """
    seed_dir = seed_dir or get_seeds_dir()
    seed_dir.mkdir(parents=True, exist_ok=True)

    seed_file = seed_dir / "seasonal_windows.csv"

    # Seasonal patterns based on Indonesian agricultural calendar
    seasonal_windows = [
        # Rice harvest season (wet season)
        {
            "commodity_id": "beras-pulen",
            "start_date": "2026-09-01",
            "end_date": "2026-10-31",
            "volatility_multiplier": 1.2,
        },
        # Corn harvest season
        {
            "commodity_id": "biji-bijian-jagung",
            "start_date": "2026-08-01",
            "end_date": "2026-10-31",
            "volatility_multiplier": 1.3,
        },
        # Cassava harvest
        {
            "commodity_id": "umbi-kecipir",
            "start_date": "2026-05-01",
            "end_date": "2026-07-31",
            "volatility_multiplier": 1.25,
        },
        # Chili harvest (varies by region)
        {
            "commodity_id": "cabai-merah-besar",
            "start_date": "2026-06-01",
            "end_date": "2026-08-31",
            "volatility_multiplier": 1.5,
        },
        # Egg production season (holiday demand)
        {
            "commodity_id": "telur-ayam",
            "start_date": "2026-03-15",
            "end_date": "2026-03-28",
            "volatility_multiplier": 1.3,
        },
        # Egg production season (Eid)
        {
            "commodity_id": "telur-ayam",
            "start_date": "2026-06-01",
            "end_date": "2026-07-15",
            "volatility_multiplier": 1.3,
        },
        # Egg production season (Nyepi)
        {
            "commodity_id": "telur-ayam",
            "start_date": "2026-03-10",
            "end_date": "2026-03-20",
            "volatility_multiplier": 1.2,
        },
        # Onions (harvest season)
        {
            "commodity_id": "bawang-merah-ukuran-besar",
            "start_date": "2026-07-01",
            "end_date": "2026-09-30",
            "volatility_multiplier": 1.4,
        },
        # Tomatoes (seasonal)
        {
            "commodity_id": "tomat-merah-ukuran-besar",
            "start_date": "2026-04-01",
            "end_date": "2026-06-30",
            "volatility_multiplier": 1.35,
        },
    ]

    lines = ["commodity_id,start_date,end_date,volatility_multiplier"]
    for sw in seasonal_windows:
        lines.append(
            f"{sw['commodity_id']},{sw['start_date']},{sw['end_date']},{sw['volatility_multiplier']}"
        )

    with Path(seed_file).open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"Wrote seasonal_windows seed to {seed_file}")


def write_all_seeds(seed_dir: Path | None = None) -> None:
    """Write all seeds."""
    write_calendar_holidays(seed_dir)
    write_seasonal_windows(seed_dir)
    print("All seeds written.")


if __name__ == "__main__":
    write_all_seeds()
