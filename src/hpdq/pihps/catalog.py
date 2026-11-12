"""Which PIHPS commodities to fetch.

Ids come from the source's ``GetRefCommodityAndCategory`` list (recorded in
tests/fixtures/pihps/). Names here are for humans only; the reference list fetched every run is
the authority, and the schema-drift check (M3) compares the two.
"""

COMMODITIES: dict[str, str] = {
    "com_1": "Beras Kualitas Bawah I",
    "com_2": "Beras Kualitas Bawah II",
    "com_3": "Beras Kualitas Medium I",
    "com_4": "Beras Kualitas Medium II",
    "com_5": "Beras Kualitas Super I",
    "com_6": "Beras Kualitas Super II",
    "com_7": "Daging Ayam Ras Segar",
    "com_8": "Daging Sapi Kualitas 1",
    "com_9": "Daging Sapi Kualitas 2",
    "com_10": "Telur Ayam Ras Segar",
    "com_11": "Bawang Merah Ukuran Sedang",
    "com_12": "Bawang Putih Ukuran Sedang",
    "com_13": "Cabai Merah Besar",
    "com_14": "Cabai Merah Keriting",
    "com_15": "Cabai Rawit Hijau",
    "com_16": "Cabai Rawit Merah",
    "com_17": "Minyak Goreng Curah",
    "com_18": "Minyak Goreng Kemasan Bermerk 1",
    "com_19": "Minyak Goreng Kemasan Bermerk 2",
    "com_20": "Gula Pasir Kualitas Premium",
    "com_21": "Gula Pasir Lokal",
}

COMMODITY_GROUPS: dict[str, tuple[str, ...]] = {
    # M1 scope: the most volatile group, so the anomaly logic is exercised early.
    "chillies": ("com_13", "com_14", "com_15", "com_16"),
    "all": tuple(COMMODITIES),
}

DEFAULT_GROUP = "chillies"


def commodities_for(group: str) -> tuple[str, ...]:
    try:
        return COMMODITY_GROUPS[group]
    except KeyError:
        known = ", ".join(sorted(COMMODITY_GROUPS))
        raise ValueError(f"unknown commodity group {group!r}; known: {known}") from None
