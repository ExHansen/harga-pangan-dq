"""Per-run request manifest: one JSON line per request outcome.

The manifest is the audit trail for politeness and reliability: it lists every request a run made,
including the ones that were deduplicated, failed or refused (which leave no raw file).

The file belongs to exactly one run: it is created exclusively when the run starts (never
overwriting anything), and each outcome is appended and flushed as soon as it is known. A run that
is killed midway therefore still leaves the record of every request it finished.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from hpdq.timeutil import compact_utc

Outcome = Literal["stored", "dedup", "exists", "failed", "refused", "skipped"]


@dataclass
class Manifest:
    path: Path
    run_id: str
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(cls, root: Path, *, run_id: str, started_at: datetime) -> "Manifest":
        path = root / "manifest" / f"{compact_utc(started_at)}__{run_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8"):  # exclusive create: fails if it exists
            pass
        return cls(path=path, run_id=run_id)

    def add(self, *, key: str, endpoint: str, outcome: Outcome, **details: Any) -> None:
        entry = {
            "run_id": self.run_id,
            "seq": len(self.entries) + 1,
            "key": key,
            "endpoint": endpoint,
            "outcome": outcome,
            **details,
        }
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
            fh.flush()
