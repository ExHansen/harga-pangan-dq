"""Per-run request manifest: one JSON line per request attempt outcome.

The manifest is the audit trail for politeness and reliability: it lists every request a run made,
including the ones that were deduplicated, failed or refused (which leave no raw file). It is
written once, at the end of the run, as a new immutable file.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from hpdq.raw.store import write_new_file
from hpdq.timeutil import compact_utc

Outcome = Literal["stored", "dedup", "failed", "refused", "skipped"]


@dataclass
class Manifest:
    run_id: str
    started_at: datetime
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, *, key: str, endpoint: str, outcome: Outcome, **details: Any) -> None:
        self.entries.append(
            {
                "run_id": self.run_id,
                "seq": len(self.entries) + 1,
                "key": key,
                "endpoint": endpoint,
                "outcome": outcome,
                **details,
            }
        )

    def path_in(self, root: Path) -> Path:
        return root / "manifest" / f"{compact_utc(self.started_at)}__{self.run_id}.jsonl"

    def write(self, root: Path) -> Path:
        path = self.path_in(root)
        lines = [json.dumps(e, sort_keys=True, ensure_ascii=False) for e in self.entries]
        write_new_file(path, ("\n".join(lines) + "\n").encode("utf-8"))
        return path
