"""Opencode R7-A2 packager: build PRIVATE Kaggle dataset+kernel staging, KHONG submit.

Doc: configs/opencode_v26_multitask.json (kien truc DONG BANG tu R5-A2, giu nguyen
sang R6-A2/R7-A2; chi doi ten driver + header, logic train byte-identical).
Output:
  artifacts/kaggle/opencode_trackA2_v26_r7/
    dataset/multitask-training-bundle.zip + dataset-metadata.json (PRIVATE)
    kernel/train.py + kernel-metadata.json (PRIVATE, T4 single)
    package-manifest.json (sha256, khong secret)
Quy tac: CHI staging o buoc nay. Submit (neu co) do buoc kiem tra
`kaggle kernels list --mine` quyet dinh: con job RUNNING/QUEUED -> KHONG submit.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATASET_SLUG = "opencode-tracka2-multitask-v26-data"
KERNEL_SLUG = "opencode-tracka2-multitask-v26"
STAGING = ROOT / "artifacts/kaggle/opencode_trackA2_v26_r7"

DATA_MEMBERS = [
    "configs/opencode_v26_multitask.json",
    "configs/swing_v15_continuous_folds.json",
    "data/processed/swing_regime_research_v4/manifest.json",
    "data/processed/swing_regime_research_v4/config.json",
    "data/processed/swing_regime_research_v4/decisions.parquet",
    "data/processed/swing_regime_research_v4/candles.parquet",
    "data/processed/swing_regime_research_v4/examples.npz",
    "scripts/opencode_r7a2_multitask_train.py",
]


def collect_src_members():
    members = []
    for path in sorted((ROOT / "src/agentic_alpha_lab").rglob("*.py")):
        members.append(path.relative_to(ROOT).as_posix())
    return members


KERNEL_TRAIN = '''"""Private single-T4 full training for v26 multitask MLP (R7-A2)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unpack(input_root):
    archives = list(input_root.rglob("multitask-training-bundle.zip"))
    if len(archives) == 1:
        bundle = Path(tempfile.mkdtemp(prefix="btc-multitask-"))
        with zipfile.ZipFile(archives[0]) as z:
            for entry in z.infolist():
                if not (bundle / entry.filename).resolve().is_relative_to(bundle.resolve()):
                    raise ValueError("Unsafe ZIP path")
            z.extractall(bundle)
    elif not archives:
        manifests = list(input_root.rglob("bundle-hashes.json"))
        if len(manifests) != 1:
            raise ValueError("Expected exactly one private bundle")
        bundle = manifests[0].parent
    else:
        raise ValueError("Ambiguous attached archive")
    hashes = json.loads((bundle / "bundle-hashes.json").read_text())
    for name, expected in hashes.items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()) or path.is_symlink() or sha(path) != expected:
            raise ValueError(f"Invalid bundle member: {name}")
    return bundle


def main():
    try:
        import torch
        names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        torch_ver = torch.__version__
    except Exception:
        names, torch_ver = [], "unavailable"
    print(json.dumps({"allocated_gpus": names, "torch": torch_ver}), flush=True)
    if names and not all("T4" in n for n in names):
        raise RuntimeError("Requires free T4 accelerator; no paid fallback")
    bundle = unpack(Path("/kaggle/input"))
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "pyarrow>=18,<24"], check=True)
    plans = [p for p in (bundle / "configs").glob("*.json")
             if json.loads(p.read_text()).get("experiment") == "opencode-v26-multitask"]
    if len(plans) != 1:
        raise ValueError("Expected exactly one registered v26 multitask plan")
    plan_path = plans[0]
    output = Path("/kaggle/working/multitask-training")
    output.mkdir(exist_ok=False)
    for source, name in ((plan_path, "plan.json"), (bundle / "bundle-hashes.json", "bundle-hashes.json")):
        shutil.copy2(source, output / name)
    shutil.copytree(bundle / "src", output / "source/src")
    shutil.copytree(bundle / "scripts", output / "source/scripts")
    shutil.copytree(bundle / "configs", output / "source/configs")
    (output / "runtime.json").write_text(json.dumps(
        {"gpus": names, "torch": torch_ver, "mode": "single-worker full 34 folds",
         "backtest_location": "in-kernel + local replay", "live_approved": False}, indent=2))
    env = dict(os.environ, PYTHONPATH=str(bundle / "src"), PYTHONUNBUFFERED="1",
               OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    started = time.monotonic()
    guard = 10800
    proc = subprocess.Popen(
        [sys.executable, str(bundle / "scripts/opencode_r7a2_multitask_train.py"),
         "--config", str(plan_path), "--output", str(output / "full")],
        cwd=bundle, env=env)
    while proc.poll() is None:
        if time.monotonic() - started > guard:
            proc.terminate()
            break
        time.sleep(5)
    code = proc.wait()
    summary = output / "full/summary.json"
    result = {"state": "complete" if code == 0 and summary.exists() else "incomplete",
              "worker_exit_code": code, "local_replay_required": True,
              "portfolio_evaluation": "in-kernel" if summary.exists() else "not_run",
              "independent_test": False, "live_approved": False}
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    if result["state"] != "complete":
        raise RuntimeError("Training incomplete; output retained, do not evaluate a subset")


if __name__ == "__main__":
    main()
'''


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    plan = json.loads((ROOT / "configs/opencode_v26_multitask.json").read_text(encoding="utf-8"))
    assert plan["experiment"] == "opencode-v26-multitask", "sai plan v26"
    assert plan["architecture"]["hidden"] == [64, 32], "kien truc phai dong bang 44->64->32"
    assert plan["architecture"]["in_features"] == 44, "in_features phai 44"
    members = list(DATA_MEMBERS) + collect_src_members()
    if a.force_fresh:
        shutil.rmtree(STAGING, ignore_errors=True)
    if STAGING.exists():
        raise FileExistsError("Chon staging moi; khong ghi de (xoa tay hoac --force-fresh)")
    (STAGING / "dataset").mkdir(parents=True)
    (STAGING / "kernel").mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="multitask-bundle-") as tmp:
        stage = Path(tmp) / "bundle"
        hashes = {}
        for name in members:
            src = ROOT / name
            if not src.exists():
                raise FileNotFoundError(f"Thieu bundle member: {name}")
            dst = stage / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            hashes[name] = sha(src)
        (stage / "bundle-hashes.json").write_text(json.dumps(hashes, indent=2))
        blob = b"".join((stage / n).read_bytes() for n in hashes if (stage / n).suffix in {".py", ".json"})
        for marker in (b"KAGGLE_API_TOKEN", b"kaggle.json", b"api_key", b"BEGIN PRIVATE"):
            if marker in blob:
                raise ValueError(f"Bundle chua marker cam: {marker!r}")
        zpath = STAGING / "dataset" / "multitask-training-bundle.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in sorted(hashes) + ["bundle-hashes.json"]:
                z.write(stage / name, name)
    (STAGING / "dataset" / "dataset-metadata.json").write_text(json.dumps({
        "id": f"<kaggle-username>/{DATASET_SLUG}", "title": DATASET_SLUG.replace("-", " "),
        "licenses": [{"name": "other"}],
        "description": "Private BTC research snapshot + allowlisted v26 multitask MLP code. No credentials. Opened development periods only."},
        indent=2))
    (STAGING / "kernel" / "train.py").write_text(KERNEL_TRAIN, encoding="utf-8")
    (STAGING / "kernel" / "kernel-metadata.json").write_text(json.dumps({
        "id": f"<kaggle-username>/{KERNEL_SLUG}", "title": KERNEL_SLUG,
        "code_file": "train.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [f"<kaggle-username>/{DATASET_SLUG}"],
        "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=2))
    manifest = {"dataset_slug": DATASET_SLUG, "kernel_slug": KERNEL_SLUG,
                "archive_sha256": sha(STAGING / "dataset" / "multitask-training-bundle.zip"),
                "archive_bytes": (STAGING / "dataset" / "multitask-training-bundle.zip").stat().st_size,
                "files": hashes, "n_files": len(hashes), "private_required": True,
                "plan": "configs/opencode_v26_multitask.json",
                "driver": "scripts/opencode_r7a2_multitask_train.py",
                "architecture": plan["architecture"],
                "submit_status": "STAGED-ONLY (cho ket qua kiem tra kernels list --mine)",
                "submit_command_later": [
                    "kaggle datasets create -p artifacts/kaggle/opencode_trackA2_v26_r7/dataset --public false (sau khi het job RUNNING/QUEUED)",
                    "kaggle kernels push -p artifacts/kaggle/opencode_trackA2_v26_r7/kernel (PRIVATE, sau khi dataset san sang)"],
                "live_approved": False}
    (STAGING / "package-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"staged": str(STAGING), "archive_bytes": manifest["archive_bytes"],
                      "archive_sha256": manifest["archive_sha256"], "n_files": len(hashes),
                      "submit": "KHONG (staged-only)"}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force-fresh", action="store_true")
    main(p.parse_args())
