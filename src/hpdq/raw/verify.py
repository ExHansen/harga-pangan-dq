"""Integrity checks for the raw store.

``verify_store`` proves every stored file is what its name and metadata claim (no tampering, no
truncation, deterministic compression). ``git_append_only_violations`` is the guard the daily
workflow runs before committing the ``data`` branch: staged changes may only *add* files.
"""

import gzip
import subprocess
from pathlib import Path

from hpdq.raw.store import (
    BODY_SUFFIX,
    META_SUFFIX,
    RawStore,
    gzip_deterministic,
    sha256_hex,
)


def verify_store(root: Path) -> list[str]:
    """Return a list of problems; empty means the store is intact."""
    problems: list[str] = []
    store = RawStore(root)
    if not store.source_root.exists():
        return problems

    for snap in store.iter_snapshots():
        rel = snap.body_path.relative_to(root).as_posix()
        if not snap.meta_path.exists():
            problems.append(f"{rel}: missing {META_SUFFIX} sidecar")
            continue
        compressed = snap.body_path.read_bytes()
        try:
            body = gzip.decompress(compressed)
        except (OSError, EOFError) as exc:
            problems.append(f"{rel}: not a valid gzip file ({exc})")
            continue
        meta = snap.read_meta()
        sha = sha256_hex(body)
        if sha != meta.get("sha256"):
            problems.append(f"{rel}: sha256 {sha[:12]} does not match metadata")
        if sha[:12] != snap.sha12:
            problems.append(f"{rel}: sha256 {sha[:12]} does not match file name")
        if len(body) != meta.get("bytes"):
            problems.append(f"{rel}: size {len(body)} does not match metadata {meta.get('bytes')}")
        if compressed != gzip_deterministic(body):
            problems.append(f"{rel}: compressed bytes are not deterministic")

    for meta_path in sorted(store.source_root.rglob(f"*{META_SUFFIX}")):
        body_path = meta_path.with_name(meta_path.name.removesuffix(META_SUFFIX) + BODY_SUFFIX)
        if not body_path.exists():
            problems.append(f"{meta_path.relative_to(root).as_posix()}: sidecar without body")

    for tmp in sorted(store.source_root.rglob(".*.tmp-*")):
        problems.append(f"{tmp.relative_to(root).as_posix()}: leftover temp file")

    return problems


def git_append_only_violations(repo_dir: Path) -> list[str]:
    """Staged changes that modify, delete, rename or retype files (only additions are allowed)."""
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "diff", "--cached", "--name-status", "--diff-filter=MDRTCUXB"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]
