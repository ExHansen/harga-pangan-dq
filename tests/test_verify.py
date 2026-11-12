import gzip
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from hpdq.pihps.specs import commodity_grid
from hpdq.raw.store import RawStore, SnapshotRef, gzip_deterministic
from hpdq.raw.verify import git_append_only_violations, verify_store
from support import fixture_bytes, grid_fixture_name, make_result

BODY = fixture_bytes(grid_fixture_name("com_13"))


@pytest.fixture
def stored(tmp_path: Path) -> SnapshotRef:
    spec = commodity_grid("com_13", date(2026, 11, 4), date(2026, 11, 11))
    return RawStore(tmp_path).put(make_result(spec, BODY), run_id="r").snapshot


def test_intact_store_has_no_problems(tmp_path: Path, stored: SnapshotRef) -> None:
    assert verify_store(tmp_path) == []


def test_tampered_body_is_detected(tmp_path: Path, stored: SnapshotRef) -> None:
    stored.body_path.write_bytes(gzip_deterministic(BODY.replace(b"70,250", b"70,999")))

    problems = verify_store(tmp_path)

    assert any("does not match metadata" in p for p in problems)
    assert any("does not match file name" in p for p in problems)


def test_truncated_body_is_detected(tmp_path: Path, stored: SnapshotRef) -> None:
    stored.body_path.write_bytes(stored.body_path.read_bytes()[:50])

    assert any("not a valid gzip" in p for p in verify_store(tmp_path))


def test_non_deterministic_compression_is_detected(tmp_path: Path, stored: SnapshotRef) -> None:
    stored.body_path.write_bytes(gzip.compress(BODY, mtime=123))

    assert any("not deterministic" in p for p in verify_store(tmp_path))


def test_missing_sidecar_orphan_sidecar_and_temp_files(tmp_path: Path, stored: SnapshotRef) -> None:
    orphan = stored.meta_path.with_name("x__20261112T000000Z__abc.meta.json")
    shutil.copy(stored.meta_path, orphan)
    stored.meta_path.unlink()
    (stored.body_path.parent / ".y.json.gz.tmp-123").write_bytes(b"")

    problems = verify_store(tmp_path)

    assert any("missing .meta.json sidecar" in p for p in problems)
    assert any("sidecar without body" in p for p in problems)
    assert any("leftover temp file" in p for p in problems)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_guard_allows_additions_only(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "a")

    (tmp_path / "b.txt").write_text("b")
    git(tmp_path, "add", "-A")
    assert git_append_only_violations(tmp_path) == []

    (tmp_path / "a.txt").write_text("changed")
    git(tmp_path, "add", "-A")
    assert git_append_only_violations(tmp_path) == ["M\ta.txt"]

    (tmp_path / "a.txt").unlink()
    git(tmp_path, "add", "-A")
    assert git_append_only_violations(tmp_path) == ["D\ta.txt"]
