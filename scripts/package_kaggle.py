"""Prepare allowlisted private Kaggle dataset + script metadata. No upload here."""
from __future__ import annotations
import torch
import argparse
import json
from pathlib import Path
import re
import shutil
import zipfile
from agentic_alpha_lab.data.training import sha256


def package(root: Path, dataset: Path, upstream: Path, output: Path, owner: str, slug: str, swing: bool = False):
    if output.exists():
        raise FileExistsError("Choose a new staging version")
    if not re.fullmatch(r"[a-z0-9_-]+", owner) or not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError("Invalid Kaggle owner/slug")
    manifest = json.loads((dataset / "manifest.json").read_text())
    if manifest["smoke_only"]:
        raise ValueError("Do not upload a smoke dataset as the full experiment")
    allowed = {"config.json", "train.npz", "validation.npz", "train_decisions.parquet",
               "validation_decisions.parquet", "development_candles.parquet"}
    if swing:
        if manifest.get("schema") not in {"kronos-base-swing-v2", "kronos-base-swing-v5"} or not manifest.get("policy_split_included"):
            raise ValueError("Expected swing dataset")
        allowed |= {"policy.npz", "policy_decisions.parquet"}
    if set(manifest["files"]) != allowed or manifest["test_included"] or manifest["calibration_included"]:
        raise ValueError("Unexpected dataset contents")
    files = {}
    for name in sorted(allowed):
        if sha256(dataset / name) != manifest["files"][name]:
            raise ValueError(f"Dataset hash mismatch: {name}")
        files[f"dataset/{name}"] = dataset / name
    files["dataset/manifest.json"] = dataset / "manifest.json"
    for path in sorted((root / "src").rglob("*.py")):
        files[path.relative_to(root).as_posix()] = path
    scripts = ("train_swing.py", "infer_swing.py") if swing else ("train_kronos_trading.py", "infer_kronos_trading.py")
    if swing and manifest["schema"] == "kronos-base-swing-v5":
        scripts += ("train_swing_v5.py", "infer_swing_v5.py")
    for name in scripts:
        files[f"scripts/{name}"] = root / "scripts" / name
    for path in sorted((upstream / "model").glob("*.py")):
        files[f"upstream/model/{path.name}"] = path
    files["upstream/LICENSE"] = upstream / "LICENSE"
    folders = ("Kronos-base", "Kronos-Tokenizer-base") if swing else ("Kronos-mini", "Kronos-Tokenizer-2k")
    for folder in folders:
        for name in ("config.json", "model.safetensors"):
            files[f"weights/{folder}/{name}"] = root / "artifacts/models" / folder / name
    hashes = {name: sha256(path) for name, path in files.items()}
    data_dir, kernel_dir = output / "dataset", output / "kernel"
    data_dir.mkdir(parents=True)
    kernel_dir.mkdir()
    archive_path = data_dir / "alpha-lab-bundle.zip"
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.write(path, name)
        archive.writestr("bundle-hashes.json", json.dumps(hashes, indent=2))
    dataset_id = f"{owner}/{slug}-data"
    (data_dir / "dataset-metadata.json").write_text(json.dumps({"id": dataset_id,
        "title": f"{slug} data", "licenses": [{"name": "other"}],
        "description": "Private BTC research training bundle. Original upstream MIT license retained. No test or credentials."}, indent=2))
    shutil.copy2(root / "scripts/kaggle_bootstrap.py", kernel_dir / "train.py")
    (kernel_dir / "kernel-metadata.json").write_text(json.dumps({"id": f"{owner}/{slug}",
        "title": slug.replace("-", " "), "code_file": "train.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True, "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [dataset_id], "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=2))
    report = {"dataset_id": dataset_id, "kernel_id": f"{owner}/{slug}", "bundle_sha256": sha256(archive_path),
              "bytes": archive_path.stat().st_size, "file_count": len(files), "test_included": False,
              "credentials_included": False, "private_required": True,
              "kernel_source_sha256": sha256(kernel_dir / "train.py"), "hashes": hashes}
    (output / "package-manifest.json").write_text(json.dumps(report, indent=2))
    return {k: v for k, v in report.items() if k != "hashes"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--swing", action="store_true")
    a = p.parse_args()
    print(json.dumps(package(Path.cwd(), a.dataset, a.upstream, a.output, a.owner, a.slug, a.swing), indent=2))
