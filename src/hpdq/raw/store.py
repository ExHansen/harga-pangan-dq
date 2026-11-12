"""Immutable, append-only storage of raw source responses.

Layout (relative to the data root, which becomes the ``data`` branch in M4)::

    raw/pihps/<partition>/fetched=<WIB date>/<key>__<UTC stamp>__<sha12>.json.gz
    raw/pihps/<partition>/fetched=<WIB date>/<key>__<UTC stamp>__<sha12>.meta.json

Guarantees:
- **Never overwrite.** Files are created with a hard link from a temp file, which fails if the
  target exists. Nothing in this module modifies or deletes a stored file.
- **Idempotent.** A response whose SHA-256 equals the *latest* stored snapshot of the same request
  is not stored again. Comparing with the latest (not any) snapshot keeps a revert A -> B -> A
  visible as three snapshots in time order.
- **Deterministic bytes.** gzip is written with ``mtime=0`` and no embedded file name, so equal
  bodies always produce equal files.
"""

import gzip
import hashlib
import io
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from hpdq import __version__
from hpdq.pihps.client import FetchResult
from hpdq.pihps.specs import RequestSpec
from hpdq.timeutil import compact_utc, iso_utc, parse_compact_utc, wib_date

SOURCE = "pihps"
BODY_SUFFIX = ".json.gz"
META_SUFFIX = ".meta.json"
META_SCHEMA_VERSION = 1


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gzip_deterministic(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(data)
    return buf.getvalue()


def write_new_file(path: Path, data: bytes) -> None:
    """Create ``path`` with ``data``; raise ``FileExistsError`` if it already exists.

    Written to a temp file first and hard-linked into place, so a crash never leaves a partial file
    under the final name.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink()


def dump_json(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


@dataclass(frozen=True)
class SnapshotRef:
    """A stored snapshot, identified by its file stem (unique, sortable, human-readable)."""

    body_path: Path
    meta_path: Path

    @property
    def snapshot_id(self) -> str:
        return self.body_path.name.removesuffix(BODY_SUFFIX)

    @property
    def key(self) -> str:
        return self.snapshot_id.rsplit("__", 2)[0]

    @property
    def fetched_at(self) -> datetime:
        return parse_compact_utc(self.snapshot_id.rsplit("__", 2)[1])

    @property
    def sha12(self) -> str:
        return self.snapshot_id.rsplit("__", 2)[2]

    def read_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return meta

    def read_body(self) -> bytes:
        return gzip.decompress(self.body_path.read_bytes())


@dataclass(frozen=True)
class PutResult:
    snapshot: SnapshotRef
    sha256: str
    created: bool


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.source_root = root / "raw" / SOURCE

    def _partition_dir(self, spec: RequestSpec) -> Path:
        return self.source_root / spec.partition

    def snapshots_for(self, spec: RequestSpec) -> list[SnapshotRef]:
        """All snapshots of one request, oldest first."""
        part = self._partition_dir(spec)
        if not part.exists():
            return []
        bodies = part.glob(f"fetched=*/{spec.key}__*{BODY_SUFFIX}")
        refs = [self._ref(p) for p in bodies if p.name.rsplit("__", 2)[0] == spec.key]
        return sorted(refs, key=lambda r: (r.fetched_at, r.snapshot_id))

    def latest(self, spec: RequestSpec) -> SnapshotRef | None:
        snaps = self.snapshots_for(spec)
        return snaps[-1] if snaps else None

    def iter_snapshots(self) -> Iterator[SnapshotRef]:
        """Every stored snapshot in a stable order (path order)."""
        if not self.source_root.exists():
            return
        for body in sorted(self.source_root.rglob(f"*{BODY_SUFFIX}")):
            yield self._ref(body)

    @staticmethod
    def _ref(body_path: Path) -> SnapshotRef:
        stem = body_path.name.removesuffix(BODY_SUFFIX)
        return SnapshotRef(body_path, body_path.with_name(stem + META_SUFFIX))

    def put(self, result: FetchResult, *, run_id: str) -> PutResult:
        spec = result.spec
        sha = sha256_hex(result.body)
        latest = self.latest(spec)
        if latest is not None and latest.read_meta().get("sha256") == sha:
            return PutResult(latest, sha, created=False)

        directory = self._partition_dir(spec) / f"fetched={wib_date(result.fetched_at)}"
        stem = f"{spec.key}__{compact_utc(result.fetched_at)}__{sha[:12]}"
        ref = SnapshotRef(directory / (stem + BODY_SUFFIX), directory / (stem + META_SUFFIX))
        meta = {
            "schema_version": META_SCHEMA_VERSION,
            "source": SOURCE,
            "endpoint": spec.endpoint.value,
            "url": spec.url,
            "params": spec.params_dict(),
            "partition": spec.partition,
            "key": spec.key,
            "fetched_at": iso_utc(result.fetched_at),
            "status_code": result.status_code,
            "content_type": result.content_type,
            "sha256": sha,
            "bytes": len(result.body),
            "elapsed_s": result.elapsed_s,
            "attempts": result.attempts,
            "user_agent": result.user_agent,
            "run_id": run_id,
            "client_version": __version__,
        }
        # Body first: a meta file never points at a body that does not exist.
        write_new_file(ref.body_path, gzip_deterministic(result.body))
        write_new_file(ref.meta_path, dump_json(meta))
        return PutResult(ref, sha, created=True)
