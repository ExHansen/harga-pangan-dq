"""The data dictionary is generated, complete, and never stale."""

import csv
import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hpdq.docs import render
from hpdq.transform import DbtPaths, dbt_project_dir, run_dbt
from support import block_network

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def manifest(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", block_network)
        paths = DbtPaths.under(tmp_path_factory.mktemp("docs"))
        assert run_dbt(["parse"], paths)
    yield json.loads((paths.target_dir / "manifest.json").read_text(encoding="utf-8"))


def documented_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        n
        for n in manifest["nodes"].values()
        if n["package_name"] == "hpdq"
        and (n["resource_type"] == "seed" or n["fqn"][1:2] == ["marts"])
    ]


def test_every_mart_and_seed_column_has_a_description(manifest: dict[str, Any]) -> None:
    missing = [
        f"{n['name']}.{column}"
        for n in documented_nodes(manifest)
        for column, spec in n["columns"].items()
        if not spec.get("description")
    ]
    assert missing == []


def test_every_seed_column_is_declared(manifest: dict[str, Any]) -> None:
    for node in documented_nodes(manifest):
        if node["resource_type"] != "seed":
            continue
        csv_path = dbt_project_dir() / node["original_file_path"]
        with csv_path.open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        assert sorted(node["columns"]) == sorted(header), node["name"]


def test_committed_data_dictionary_is_up_to_date(manifest: dict[str, Any]) -> None:
    committed = (REPO / "docs" / "data-dictionary.md").read_text(encoding="utf-8")

    assert committed == render(manifest), "run `uv run hpdq docs` and commit the result"
