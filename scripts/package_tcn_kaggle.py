"""Allowlisted private training bundle; never recursively packages the workspace."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(plan_path):
    plan = json.loads(plan_path.read_text())
    paths = [plan_path, ROOT / plan["parent_plan"]]
    dataset, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    for name in ("manifest.json", "config.json", "decisions.parquet", "examples.npz"):
        paths.append(dataset / name)
    for name in ("manifest.json", "decisions.parquet", "sequences.npy"):
        paths.append(cache / name)
    for name in ("tcn_fusion_value.py", "temporal_value.py", "macro_micro_value.py",
                 "hurdle_temporal_value.py", "hurdle_ranked_loss.py",
                 "residual_temporal_value.py", "residual_ranked_loss.py",
                 "top_action_loss.py", "action_margin_value.py",
                 "action_margin_loss.py"):
        paths.append(ROOT / "src/agentic_alpha_lab/models" / name)
    # Namespace packages work without an __init__; include actual initializers if present.
    paths += [p for p in (ROOT / "src/agentic_alpha_lab/__init__.py", ROOT / "src/agentic_alpha_lab/models/__init__.py") if p.exists()]
    paths.append(ROOT / "scripts/train_tcn_kaggle.py")
    if plan.get("cloud_driver"):
        if plan["cloud_driver"] not in {"train_tcn_validated.py", "train_tcn_ranked.py",
                                         "train_tcn_listwise.py", "train_tcn_ranked_gate.py",
                                         "train_gru_ranked.py", "train_gru_hurdle.py",
                                         "train_gru_residual.py", "train_gru_top_action.py",
                                         "train_gru_action_margin.py"}:
            raise ValueError("Cloud driver is not allowlisted")
        paths.append(ROOT / "scripts" / plan["cloud_driver"])
        if plan["cloud_driver"] == "train_tcn_validated.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/temporal_validation.py")
        elif plan["cloud_driver"] in {"train_tcn_ranked.py", "train_gru_ranked.py"}:
            paths.append(ROOT / "src/agentic_alpha_lab/models/ranked_loss.py")
        elif plan["cloud_driver"] == "train_tcn_listwise.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/listwise_loss.py")
        elif plan["cloud_driver"] == "train_gru_hurdle.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/ranked_loss.py")
        elif plan["cloud_driver"] == "train_gru_residual.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/ranked_loss.py")
        elif plan["cloud_driver"] == "train_gru_top_action.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/top_action_loss.py")
        elif plan["cloud_driver"] == "train_gru_action_margin.py":
            paths.append(ROOT / "src/agentic_alpha_lab/models/action_margin_value.py")
            paths.append(ROOT / "src/agentic_alpha_lab/models/action_margin_loss.py")
        else:
            paths.append(ROOT / "src/agentic_alpha_lab/models/ranked_loss.py")
            paths.append(ROOT / "src/agentic_alpha_lab/models/ranked_gate_loss.py")
    paths = list(dict.fromkeys(paths))
    for path in paths:
        if not path.resolve().is_relative_to(ROOT) or not path.is_file() or path.is_symlink():
            raise ValueError(f"Unsafe/missing bundle member: {path.name}")
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name in ("config.json", "decisions.parquet", "examples.npz"):
        if digest(dataset / name) != manifest["files"][name]:
            raise ValueError("Dataset hash changed")
    cm = json.loads((cache / "manifest.json").read_text())
    if cm["state"] != "complete" or cm["dataset_manifest_sha256"] != digest(dataset / "manifest.json"):
        raise ValueError("Sequence cache identity mismatch")
    for name, value in cm["files"].items():
        if digest(cache / name) != value:
            raise ValueError("Sequence cache changed")
    return paths


def main(a):
    if not re.fullmatch(r"[a-z0-9-]+", a.slug) or not re.fullmatch(r"[a-z0-9-]+", a.owner):
        raise ValueError("Invalid Kaggle ID")
    paths = collect(a.plan.resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    dataset, kernel = a.output / "dataset", a.output / "kernel"
    dataset.mkdir(); kernel.mkdir()
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}
    archive = dataset / "tcn-training-bundle.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            z.write(path, path.relative_to(ROOT).as_posix())
        z.writestr("bundle-hashes.json", json.dumps(hashes, indent=2))
    dataset_id = f"{a.owner}/{a.slug}-data"
    dm = {"id": dataset_id, "title": a.slug + " data", "licenses": [{"name": "other"}],
          "description": "Private BTC research snapshot and allowlisted training code. No credentials. Opened development periods only."}
    (dataset / "dataset-metadata.json").write_text(json.dumps(dm, indent=2))
    shutil.copy2(ROOT / "scripts/kaggle_tcn_bootstrap.py", kernel / "train.py")
    km = {"id": f"{a.owner}/{a.slug}", "title": a.slug, "code_file": "train.py", "language": "python",
          "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
          "machine_shape": "NvidiaTeslaT4", "dataset_sources": [dataset_id],
          "competition_sources": [], "kernel_sources": [], "model_sources": []}
    (kernel / "kernel-metadata.json").write_text(json.dumps(km, indent=2))
    record = {"dataset": dataset_id, "kernel": km["id"], "archive_sha256": digest(archive),
              "archive_bytes": archive.stat().st_size, "files": hashes, "private_required": True,
              "plan": a.plan.resolve().relative_to(ROOT).as_posix(), "bootstrap_sha256": digest(kernel / "train.py")}
    (a.output / "package-manifest.json").write_text(json.dumps(record, indent=2))
    print(json.dumps({k: v for k, v in record.items() if k != "files"}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/swing_v19_tcn_fusion.json")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--owner", default="nguynchtrai")
    p.add_argument("--slug", default="btc-swing-v19-tcn-20260906")
    main(p.parse_args())
