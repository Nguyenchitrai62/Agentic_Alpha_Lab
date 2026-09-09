import argparse
import copy
import json

import pytest

from scripts.parallel_registry import command_assign, load_registry, validate_registry


def test_parallel_registry_has_three_distinct_active_tracks():
    registry = load_registry()
    summary = validate_registry(registry)
    assert summary["active_count"] == 3
    active = [entry for entry in registry["experiments"] if entry["status"] in {"registered", "running"}]
    assert {entry["track"] for entry in active} == {"A", "B", "C"}
    assert summary["next_version"] > max(int(entry["version"][1:]) for entry in registry["experiments"])


def test_parallel_registry_rejects_duplicate_direction_key():
    registry = load_registry()
    duplicate = copy.deepcopy(registry["experiments"][0])
    duplicate["version"] = f"v{registry['next_version']}"
    registry["experiments"].append(duplicate)
    with pytest.raises(ValueError, match="Duplicate or missing direction key"):
        validate_registry(registry)


def test_parallel_registry_rejects_reused_historical_version():
    registry = load_registry()
    duplicate = copy.deepcopy(registry["experiments"][0])
    duplicate["version"] = "v44"
    duplicate["direction_key"] = "new-but-invalid-v44"
    registry["experiments"].append(duplicate)
    with pytest.raises(ValueError, match="Experiment version already used"):
        validate_registry(registry)


def test_parallel_registry_assigns_each_worker_once(tmp_path):
    registry = load_registry()
    active = [entry for entry in registry["experiments"] if entry["status"] in {"registered", "running"}]
    for entry in active:
        entry["status"] = "registered"
        entry["worker_agent_id"] = None
        entry["worker_host_id"] = None
    registry["active_round"]["status"] = "registered"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    args = argparse.Namespace(
        registry=path,
        version=active[0]["version"],
        worker_agent_id="worker-a",
        worker_host_id="local",
    )
    assert command_assign(args) == 0
    assigned = load_registry(path)
    assigned_entry = next(entry for entry in assigned["experiments"] if entry["version"] == active[0]["version"])
    assert assigned_entry["status"] == "running"
    assert assigned_entry["worker_agent_id"] == "worker-a"

    duplicate = argparse.Namespace(
        registry=path,
        version=active[1]["version"],
        worker_agent_id="worker-a",
        worker_host_id="local",
    )
    with pytest.raises(ValueError, match="already assigned"):
        command_assign(duplicate)
