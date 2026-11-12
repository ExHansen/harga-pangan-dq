"""Shape fingerprint of a raw PIHPS payload.

The fingerprint answers "does this response still look like what we parse?". It feeds the
schema-drift check (M3) and decides which snapshots the flattener may read. It never raises on bad
input: a broken payload is a finding, not a crash.

Expected shape (every PIHPS endpoint we use)::

    {"data": [ {<row>}, {<row>}, ... ]}

Grid rows carry ``no``, ``name``, ``level`` plus one key per date (``dd/mm/yyyy``) whose value is a
price string such as ``"16,500"`` or ``"-"`` for missing.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

DATE_KEY = re.compile(r"^\d{2}/\d{2}/\d{4}$")

Status = Literal["ok", "invalid_json", "unexpected_shape"]


@dataclass(frozen=True)
class Fingerprint:
    status: Status
    error: str | None = None
    top_level_keys: tuple[str, ...] = ()
    row_count: int = 0
    row_keys: tuple[str, ...] = ()
    date_key_count: int = 0
    levels: tuple[str, ...] = ()
    value_types: tuple[str, ...] = ()


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def inspect_payload(body: bytes) -> Fingerprint:
    try:
        doc = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return Fingerprint(status="invalid_json", error=f"{type(exc).__name__}: {exc}"[:300])

    if not isinstance(doc, dict):
        return Fingerprint(status="unexpected_shape", error=f"top level is {_json_type(doc)}")
    top_keys = tuple(sorted(doc))
    data = doc.get("data")
    if not isinstance(data, list):
        return Fingerprint(
            status="unexpected_shape",
            error=f"'data' is {_json_type(data) if 'data' in doc else 'missing'}",
            top_level_keys=top_keys,
        )

    row_keys: set[str] = set()
    date_keys: set[str] = set()
    levels: set[str] = set()
    value_types: set[str] = set()
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            return Fingerprint(
                status="unexpected_shape",
                error=f"row {i} is {_json_type(row)}",
                top_level_keys=top_keys,
                row_count=len(data),
            )
        for key, value in row.items():
            if DATE_KEY.match(key):
                date_keys.add(key)
                value_types.add(_json_type(value))
            else:
                row_keys.add(key)
        if "level" in row:
            levels.add(json.dumps(row["level"]))

    return Fingerprint(
        status="ok",
        top_level_keys=top_keys,
        row_count=len(data),
        row_keys=tuple(sorted(row_keys)),
        date_key_count=len(date_keys),
        levels=tuple(sorted(levels)),
        value_types=tuple(sorted(value_types)),
    )
