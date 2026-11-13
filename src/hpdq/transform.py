"""Run the dbt project (dbt-duckdb) in-process with paths pointing into the build directory.

Everything dbt writes (warehouse, target/, logs/) goes under the disposable build directory, so the
repository stays clean and a rebuild from raw is always ``rm -rf build && hpdq build``.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DBT_DIR_ENV = "HPDQ_DBT_DIR"


def dbt_project_dir() -> Path:
    """``$HPDQ_DBT_DIR`` or the ``dbt/`` folder next to ``src/`` (also true in the Docker image)."""
    override = os.environ.get(DBT_DIR_ENV)
    return Path(override) if override else Path(__file__).resolve().parents[2] / "dbt"


@dataclass(frozen=True)
class DbtPaths:
    parsed_dir: Path
    warehouse: Path
    target_dir: Path
    log_dir: Path

    @classmethod
    def under(cls, build_dir: Path) -> "DbtPaths":
        build = build_dir.resolve()
        return cls(
            parsed_dir=build / "parsed",
            warehouse=build / "warehouse.duckdb",
            target_dir=build / "dbt" / "target",
            log_dir=build / "dbt" / "logs",
        )

    def env(self) -> dict[str, str]:
        return {
            "HPDQ_PARSED_DIR": self.parsed_dir.as_posix(),
            "HPDQ_WAREHOUSE": self.warehouse.as_posix(),
            "DBT_TARGET_PATH": self.target_dir.as_posix(),
            "DBT_LOG_PATH": self.log_dir.as_posix(),
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",  # no telemetry; tests also block network
        }


@contextmanager
def _environ(values: dict[str, str]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _release_duckdb() -> None:
    """Close the DuckDB database dbt-duckdb keeps open in this process after a run.

    dbt-duckdb caches one environment per process (``DuckDBConnectionManager._ENV``, dbt-duckdb
    1.11.1, pinned). Left open, the next ``duckdb.connect`` to the warehouse in the same process
    (the checks, tests) fails with "different configuration than existing connections".
    """
    from dbt.adapters.duckdb.connections import DuckDBConnectionManager

    env = DuckDBConnectionManager._ENV
    if env is not None:
        env.close()  # type: ignore[no-untyped-call]  # dbt-duckdb ships without type hints
    DuckDBConnectionManager.close_all_connections()  # type: ignore[no-untyped-call]


def run_dbt(args: list[str], paths: DbtPaths) -> bool:
    """Invoke dbt with ``args`` (e.g. ``["build"]``); return True on success."""
    from dbt.cli.main import dbtRunner  # imported lazily: dbt is slow to import

    project = dbt_project_dir()
    paths.warehouse.parent.mkdir(parents=True, exist_ok=True)
    with _environ(paths.env()):
        try:
            result = dbtRunner().invoke(
                [*args, "--project-dir", str(project), "--profiles-dir", str(project)]
            )
        finally:
            _release_duckdb()
    return bool(result.success)
