"""Version and duplicate guard for the parallel research coordinator.

The registry is intentionally small and JSON-based so workers can inspect it
without importing the training stack. Workers should register before changing
code or consuming cloud quota; only the coordinator should serialize results.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "research" / "parallel" / "registry.json"
VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Unsupported parallel registry schema")
    return value


def version_number(value: str) -> int:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid experiment version: {value!r}")
    return int(match.group(1))


def closed_versions(registry: dict) -> set[int]:
    versions: set[int] = set()
    for item in registry.get("history", {}).get("closed_version_ranges", []):
        start, end = int(item["start"]), int(item["end"])
        if start < 1 or end < start:
            raise ValueError("Invalid closed version range")
        versions.update(range(start, end + 1))
    return versions


def canonical_entry(entry: dict) -> dict[str, str]:
    """Fields that define a research direction for duplicate detection."""
    return {
        key: str(entry.get(key, "")).strip().lower()
        for key in (
            "track",
            "direction_key",
            "model_family",
            "objective",
            "data_contract",
            "policy_contract",
        )
    }


def fingerprint(entry: dict) -> str:
    payload = json.dumps(canonical_entry(entry), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_registry(registry: dict) -> dict:
    control = registry.get("control", {})
    if control.get("coordinator_model") != "gpt-5.6-sol" or control.get("coordinator_reasoning") != "high":
        raise ValueError("Coordinator must remain gpt-5.6-sol/high")
    if control.get("worker_model") != "gpt-5.6-luna" or control.get("worker_reasoning") != "max":
        raise ValueError("Workers must remain gpt-5.6-luna/max")
    if int(control.get("default_parallel_workers", 0)) != 3:
        raise ValueError("Default parallel worker count must be exactly 3")

    experiments = registry.get("experiments")
    if not isinstance(experiments, list):
        raise ValueError("experiments must be a list")
    versions = closed_versions(registry)
    direction_keys = {str(x).strip().lower() for x in registry.get("history", {}).get("known_direction_keys", [])}
    seen_versions: set[int] = set()
    seen_fingerprints: set[str] = set()
    active = []
    for entry in experiments:
        if not isinstance(entry, dict):
            raise ValueError("Experiment entries must be objects")
        number = version_number(str(entry.get("version", "")))
        if number in versions or number in seen_versions:
            raise ValueError(f"Experiment version already used: v{number}")
        seen_versions.add(number)
        direction = str(entry.get("direction_key", "")).strip().lower()
        if not direction or direction in direction_keys:
            raise ValueError(f"Duplicate or missing direction key: {direction!r}")
        direction_keys.add(direction)
        digest = fingerprint(entry)
        if digest in seen_fingerprints:
            raise ValueError(f"Duplicate experiment fingerprint: {entry['version']}")
        seen_fingerprints.add(digest)
        if entry.get("status") in {"registered", "running"}:
            active.append(entry)

    round_info = registry.get("active_round", {})
    if int(round_info.get("expected_workers", 0)) != 3:
        raise ValueError("Active round must reserve exactly three workers")
    if len(active) != 3:
        raise ValueError(f"Active round must contain exactly three registered/running experiments, found {len(active)}")
    if {entry.get("track") for entry in active} != {"A", "B", "C"}:
        raise ValueError("Active experiments must cover tracks A, B and C exactly once")
    next_version = int(registry.get("next_version", 0))
    maximum_known = max((*versions, *seen_versions), default=0)
    if next_version <= maximum_known:
        raise ValueError("next_version must be above all known versions")
    return {
        "active_count": len(active),
        "active_versions": [entry["version"] for entry in active],
        "next_version": next_version,
        "known_closed_versions": len(versions),
    }


def save_registry(path: Path, registry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(encoded)
        temporary = Path(stream.name)
    temporary.replace(path)


def command_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    print(json.dumps(validate_registry(registry), indent=2))
    return 0


def command_inventory(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    summary = validate_registry(registry)
    print(json.dumps({
        **summary,
        "round_id": registry["active_round"]["round_id"],
        "coordinator": registry["control"],
        "experiments": [
            {"version": e["version"], "track": e["track"], "status": e["status"],
             "direction_key": e["direction_key"], "worker_agent_id": e.get("worker_agent_id")}
            for e in registry["experiments"]
        ],
    }, indent=2, ensure_ascii=False))
    return 0


def command_assign(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    validate_registry(registry)
    matches = [entry for entry in registry["experiments"] if entry["version"] == args.version]
    if len(matches) != 1:
        raise ValueError(f"Unknown experiment version: {args.version}")
    if any(
        entry.get("worker_agent_id") == args.worker_agent_id
        for entry in registry["experiments"]
        if entry is not matches[0] and entry.get("status") in {"registered", "running"}
    ):
        raise ValueError(f"Worker is already assigned: {args.worker_agent_id}")
    entry = matches[0]
    if entry.get("status") not in {"registered", "running"}:
        raise ValueError(f"Cannot assign a worker while status is {entry.get('status')!r}")
    existing = entry.get("worker_agent_id")
    if existing not in {None, args.worker_agent_id}:
        raise ValueError(f"{args.version} is already assigned to {existing}")
    entry["worker_agent_id"] = args.worker_agent_id
    entry["worker_host_id"] = args.worker_host_id
    entry["status"] = "running"
    entry["assigned_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if all(item.get("status") == "running" for item in registry["experiments"]):
        registry["active_round"]["status"] = "running"
    registry["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    save_registry(args.registry, registry)
    print(json.dumps({
        "assigned": args.version,
        "worker_agent_id": args.worker_agent_id,
        "worker_host_id": args.worker_host_id,
        "round_status": registry["active_round"]["status"],
    }, indent=2))
    return 0


def load_audited_manifest(path: Path, *, version: str, track: str, parent_commit: str) -> tuple[dict, str]:
    raw = path.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("experiment_id") != version or manifest.get("track") != track:
        raise ValueError("Result manifest experiment/track does not match the registry entry")
    if manifest.get("parent_commit") != parent_commit:
        raise ValueError("Result manifest parent commit does not match the registry round")
    if manifest.get("status") not in {"audited", "accepted", "rejected"}:
        raise ValueError("Only audited, accepted or rejected results may be aggregated")
    audit = manifest.get("audit", {})
    if audit.get("passed") is not True or audit.get("replay_complete") is not True:
        raise ValueError("Only complete results that passed the leader audit may be aggregated")
    if manifest.get("live_approved") is not False:
        raise ValueError("Parallel research results must remain not live-approved")
    return manifest, hashlib.sha256(raw).hexdigest()


def command_rotate(args: argparse.Namespace) -> int:
    """Atomically close one audited experiment and assign its worker a successor."""

    registry = load_registry(args.registry)
    validate_registry(registry)
    matches = [entry for entry in registry["experiments"] if entry["version"] == args.completed_version]
    if len(matches) != 1:
        raise ValueError(f"Unknown completed experiment: {args.completed_version}")
    completed = matches[0]
    if completed.get("status") not in {"registered", "running"}:
        raise ValueError(f"Experiment is already closed: {args.completed_version}")
    manifest, manifest_sha256 = load_audited_manifest(
        args.result_manifest,
        version=args.completed_version,
        track=completed["track"],
        parent_commit=registry["active_round"]["parent_commit"],
    )
    if args.track != completed["track"]:
        raise ValueError("A successor must stay on the completed worker's track")
    number = version_number(args.version)
    if number < int(registry["next_version"]):
        raise ValueError(f"Version must be v{registry['next_version']} or higher")
    candidate = {
        "version": args.version,
        "track": args.track,
        "direction_key": args.direction_key,
        "status": "running",
        "parent_versions": args.parent_version,
        "model_family": args.model_family,
        "objective": args.objective,
        "data_contract": args.data_contract,
        "policy_contract": args.policy_contract,
        "hypothesis": args.hypothesis,
        "parent_commit": registry["active_round"]["parent_commit"],
        "write_scope": f"research/parallel/rounds/{registry['active_round']['round_id']}/{args.version}",
        "worker_agent_id": completed.get("worker_agent_id"),
        "worker_host_id": completed.get("worker_host_id"),
        "result_manifest": None,
        "registered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assigned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    used_versions = closed_versions(registry) | {version_number(e["version"]) for e in registry["experiments"]}
    if number in used_versions:
        raise ValueError(f"Experiment version already used: {args.version}")
    keys = {x.lower() for x in registry["history"].get("known_direction_keys", [])}
    keys.update(e["direction_key"].lower() for e in registry["experiments"])
    if args.direction_key.lower() in keys:
        raise ValueError(f"Direction already registered: {args.direction_key}")
    if any(fingerprint(entry) == fingerprint(candidate) for entry in registry["experiments"]):
        raise ValueError("Canonical experiment fingerprint already registered")

    completed["status"] = manifest["status"]
    completed["result_manifest"] = str(args.result_manifest)
    completed["result_manifest_sha256"] = manifest_sha256
    completed["result_summary"] = {
        "scenarios": manifest["scenarios"],
        "independent_test": manifest["independent_test"],
        "live_approved": manifest["live_approved"],
        "audit_notes": manifest["audit"]["notes"],
    }
    completed["audited_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    registry["experiments"].append(candidate)
    registry["next_version"] = max(int(registry["next_version"]), number + 1)
    registry["active_round"]["version_range"][1] = max(
        int(registry["active_round"]["version_range"][1]), number
    )
    registry["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    validate_registry(registry)
    save_registry(args.registry, registry)
    print(json.dumps({
        "closed": args.completed_version,
        "status": manifest["status"],
        "successor": args.version,
        "worker_agent_id": candidate["worker_agent_id"],
        "result_manifest_sha256": manifest_sha256,
    }, indent=2))
    return 0


def command_register(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    validate_registry(registry)
    number = version_number(args.version)
    if number < int(registry["next_version"]):
        raise ValueError(f"Version must be v{registry['next_version']} or higher")
    candidate = {
        "version": args.version,
        "track": args.track,
        "direction_key": args.direction_key,
        "status": "registered",
        "parent_versions": args.parent_version,
        "model_family": args.model_family,
        "objective": args.objective,
        "data_contract": args.data_contract,
        "policy_contract": args.policy_contract,
        "hypothesis": args.hypothesis,
        "parent_commit": registry["active_round"]["parent_commit"],
        "write_scope": f"research/parallel/rounds/{registry['active_round']['round_id']}/{args.version}",
        "worker_agent_id": None,
        "result_manifest": None,
        "registered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    used_versions = closed_versions(registry) | {version_number(e["version"]) for e in registry["experiments"]}
    if number in used_versions:
        raise ValueError(f"Experiment version already used: {args.version}")
    keys = {x.lower() for x in registry["history"].get("known_direction_keys", [])}
    keys.update(e["direction_key"].lower() for e in registry["experiments"])
    if args.direction_key.lower() in keys:
        raise ValueError(f"Direction already registered: {args.direction_key}")
    digest = fingerprint(candidate)
    if any(fingerprint(e) == digest for e in registry["experiments"]):
        raise ValueError("Canonical experiment fingerprint already registered")
    registry["experiments"].append(candidate)
    registry["next_version"] = max(int(registry["next_version"]), number + 1)
    validate_registry(registry)
    save_registry(args.registry, registry)
    print(json.dumps({"registered": args.version, "fingerprint": digest}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    commands = root.add_subparsers(dest="command", required=True)
    for name, handler in (("validate", command_validate), ("inventory", command_inventory)):
        sub = commands.add_parser(name)
        sub.set_defaults(handler=handler)
    assign = commands.add_parser("assign")
    assign.set_defaults(handler=command_assign)
    assign.add_argument("--version", required=True)
    assign.add_argument("--worker-agent-id", required=True)
    assign.add_argument("--worker-host-id")
    register = commands.add_parser("register")
    register.set_defaults(handler=command_register)
    register.add_argument("--version", required=True)
    register.add_argument("--track", choices=("A", "B", "C"), required=True)
    register.add_argument("--direction-key", required=True)
    register.add_argument("--model-family", required=True)
    register.add_argument("--objective", required=True)
    register.add_argument("--data-contract", required=True)
    register.add_argument("--policy-contract", required=True)
    register.add_argument("--hypothesis", required=True)
    register.add_argument("--parent-version", action="append", default=[])
    rotate = commands.add_parser("rotate")
    rotate.set_defaults(handler=command_rotate)
    rotate.add_argument("--completed-version", required=True)
    rotate.add_argument("--result-manifest", type=Path, required=True)
    rotate.add_argument("--version", required=True)
    rotate.add_argument("--track", choices=("A", "B", "C"), required=True)
    rotate.add_argument("--direction-key", required=True)
    rotate.add_argument("--model-family", required=True)
    rotate.add_argument("--objective", required=True)
    rotate.add_argument("--data-contract", required=True)
    rotate.add_argument("--policy-contract", required=True)
    rotate.add_argument("--hypothesis", required=True)
    rotate.add_argument("--parent-version", action="append", default=[])
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"parallel registry error: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
