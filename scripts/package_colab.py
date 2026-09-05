"""Build an allowlisted training bundle; never include the held-out test/candles."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from agentic_alpha_lab.data.training import sha256


def package(root: Path, dataset: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Choose a new bundle name")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    files = {str(path.relative_to(root)).replace("\\", "/"): path for path in sorted((root / "src").rglob("*.py"))}
    for name in ("pyproject.toml", "README.md", "requirements.txt", "scripts/train_baseline.py"):
        files[name] = root / name
    for name in ("train.parquet", "validation.parquet", "calibration.parquet", "training.yaml"):
        path = dataset / name
        if sha256(path) != manifest["files"][name]:
            raise ValueError(f"Dataset changed: {name}")
        files[f"dataset/{name}"] = path
    files["dataset/manifest.json"] = dataset / "manifest.json"
    hashes = {name: sha256(path) for name, path in files.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.write(path, name)
        archive.writestr("bundle-hashes.json", json.dumps(hashes, indent=2))
    return {"output": str(output), "sha256": sha256(output), "files": len(files),
            "test_included": False, "candles_included": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(Path.cwd(), args.dataset, args.output), indent=2))
