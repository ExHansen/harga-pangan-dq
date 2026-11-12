"""Raw store -> two lossless Parquet tables.

``snapshots.parquet``: one row per stored snapshot (sidecar provenance + shape fingerprint).
``raw_cells.parquet``: one row per (snapshot, row, field) of every snapshot whose shape is ``ok``.
Values are kept as the source sent them (JSON text, JSON type, and unquoted text), so nothing is
lost and nothing is interpreted here. Row order is preserved in ``row_idx``; it matters because
city rows follow their province row and do not name it.

The whole output is rebuilt from raw on every call (ADR-003).
"""

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from hpdq.load.inspect import inspect_payload
from hpdq.raw.store import RawStore

SNAPSHOTS_DDL = """
CREATE TABLE snapshots (
    snapshot_id     VARCHAR NOT NULL PRIMARY KEY,
    rel_path        VARCHAR NOT NULL,
    source          VARCHAR,
    endpoint        VARCHAR,
    partition_path  VARCHAR,
    request_key     VARCHAR,
    params_json     VARCHAR,
    fetched_at      TIMESTAMPTZ,
    sha256          VARCHAR,
    bytes           BIGINT,
    run_id          VARCHAR,
    client_version  VARCHAR,
    status          VARCHAR NOT NULL,
    error           VARCHAR,
    top_level_keys  VARCHAR[],
    row_count       INTEGER,
    row_keys        VARCHAR[],
    date_key_count  INTEGER,
    levels          VARCHAR[],
    value_types     VARCHAR[]
)
"""

CELLS_DDL = """
CREATE TABLE raw_cells (
    snapshot_id  VARCHAR NOT NULL,
    row_idx      INTEGER NOT NULL,
    field        VARCHAR NOT NULL,
    value_json   VARCHAR,
    value_type   VARCHAR,
    value_text   VARCHAR
)
"""

CELLS_INSERT = """
INSERT INTO raw_cells
SELECT
    m.snapshot_id,
    CAST(r.key AS INTEGER) AS row_idx,
    c.key AS field,
    CAST(c.value AS VARCHAR) AS value_json,
    c.type AS value_type,
    CASE
        WHEN c.type = 'VARCHAR' THEN c.value ->> '$'
        WHEN c.type = 'NULL' THEN NULL
        ELSE CAST(c.value AS VARCHAR)
    END AS value_text
FROM read_json_objects({files}, filename = true, format = 'unstructured') AS f
JOIN file_map AS m ON m.path = f.filename
CROSS JOIN json_each(f.json, '$.data') AS r
CROSS JOIN json_each(r.value) AS c
"""


@dataclass(frozen=True)
class LoadSummary:
    snapshots: int
    ok: int
    not_ok: int
    cells: int
    snapshots_path: Path
    cells_path: Path


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_parsed(data_root: Path, out_dir: Path) -> LoadSummary:
    store = RawStore(data_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(SNAPSHOTS_DDL)
        con.execute(CELLS_DDL)
        con.execute("CREATE TABLE file_map (path VARCHAR PRIMARY KEY, snapshot_id VARCHAR)")

        ok_files: list[tuple[str, str]] = []
        rows: list[tuple[object, ...]] = []
        for snap in store.iter_snapshots():
            rel = snap.body_path.relative_to(data_root).as_posix()
            meta = snap.read_meta() if snap.meta_path.exists() else {}
            fp = inspect_payload(snap.read_body())
            status = fp.status if meta else "missing_meta"
            rows.append(
                (
                    snap.snapshot_id,
                    rel,
                    meta.get("source"),
                    meta.get("endpoint"),
                    meta.get("partition"),
                    meta.get("key", snap.key),
                    json.dumps(meta.get("params", {}), sort_keys=True),
                    meta.get("fetched_at"),
                    meta.get("sha256"),
                    meta.get("bytes"),
                    meta.get("run_id"),
                    meta.get("client_version"),
                    status,
                    fp.error,
                    list(fp.top_level_keys),
                    fp.row_count,
                    list(fp.row_keys),
                    fp.date_key_count,
                    list(fp.levels),
                    list(fp.value_types),
                )
            )
            if status == "ok":
                ok_files.append((snap.body_path.resolve().as_posix(), snap.snapshot_id))

        if rows:
            placeholders = ", ".join(["?"] * len(rows[0]))
            con.executemany(f"INSERT INTO snapshots VALUES ({placeholders})", rows)
        if ok_files:
            con.executemany("INSERT INTO file_map VALUES (?, ?)", ok_files)
            files_sql = "[" + ", ".join(_sql_str(p) for p, _ in ok_files) + "]"
            con.execute(CELLS_INSERT.format(files=files_sql))

        snapshots_path = out_dir / "snapshots.parquet"
        cells_path = out_dir / "raw_cells.parquet"
        con.execute(
            f"COPY (SELECT * FROM snapshots ORDER BY snapshot_id) "
            f"TO {_sql_str(snapshots_path.as_posix())} (FORMAT parquet, COMPRESSION zstd)"
        )
        con.execute(
            f"COPY (SELECT * FROM raw_cells ORDER BY snapshot_id, row_idx, field) "
            f"TO {_sql_str(cells_path.as_posix())} (FORMAT parquet, COMPRESSION zstd)"
        )
        cells_row = con.execute("SELECT count(*) FROM raw_cells").fetchone()
        cells = int(cells_row[0]) if cells_row else 0
    finally:
        con.close()

    ok = len(ok_files)
    return LoadSummary(
        snapshots=len(rows),
        ok=ok,
        not_ok=len(rows) - ok,
        cells=cells,
        snapshots_path=snapshots_path,
        cells_path=cells_path,
    )
