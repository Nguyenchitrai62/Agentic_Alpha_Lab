"""Opencode R48-M packager v132: build PRIVATE Kaggle dataset+kernel staging, KHONG submit.

Doc: configs/opencode_v132_attndistill.json (dong bang truoc). Output:
  artifacts/kaggle/opencode_trackM_v132/
    dataset/attndistill-training-bundle.zip + dataset-metadata.json (PRIVATE)
    kernel/train.py + kernel-metadata.json (PRIVATE T4x2)
    package-manifest.json (sha256, khong secret)
Bundle FROZEN soft_targets.npz (bytes-identical distill artifact, verify sha256).
Quy tac: chi staging o day; submit (dataset create + kernels push) do worker
thuc hien RIENG sau khi xac minh (a) NO RUNNING/QUEUED EITHER ACCOUNT VA
(b) student v106 terminal. Max ONE submission. Dataset-ready gate + gap >=60s.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OWNER = "nguynchtrai"
DATASET_SLUG = "opencode-trackm-attndistill-v132-data"
KERNEL_SLUG = "opencode-trackm-attndistill-v132"
ARCHIVE = "attndistill-training-bundle.zip"
SOFT_FILE = "artifacts/research/opencode_v101_distill/soft_targets.npz"
SOFT_SHA = "ff170795dde5342e5becd401e727daa10c0025a57047c07a9f1217e912556ae1"

BUNDLE_MEMBERS = [
    "configs/opencode_v132_attndistill.json",
    "configs/swing_v15_continuous_folds.json",
    "data/processed/swing_regime_research_v4/manifest.json",
    "data/processed/swing_regime_research_v4/config.json",
    "data/processed/swing_regime_research_v4/decisions.parquet",
    "data/processed/swing_regime_research_v4/candles.parquet",
    "data/processed/swing_regime_research_v4/examples.npz",
    "artifacts/features/swing_sequences_v13_20260905/manifest.json",
    "artifacts/features/swing_sequences_v13_20260905/decisions.parquet",
    "artifacts/features/swing_sequences_v13_20260905/sequences.npy",
    "artifacts/features/btc_derivatives_lag48_v1/manifest.json",
    "artifacts/features/btc_derivatives_lag48_v1/features.npz",
    "data/raw/opencode_funding_20260907/manifest.json",
    "data/raw/opencode_funding_20260907/funding_BTCUSDT.parquet",
    "data/raw/opencode_macro_yahoo_20220101_20260907/manifest.json",
    "data/raw/opencode_macro_yahoo_20220101_20260907/spy.parquet",
    "data/raw/opencode_macro_yahoo_20220101_20260907/dxy.parquet",
    SOFT_FILE,
    "src/agentic_alpha_lab/__init__.py",
    "src/agentic_alpha_lab/models/__init__.py",
    "src/agentic_alpha_lab/models/ranked_loss.py",
    "src/agentic_alpha_lab/models/temporal_validation.py",
    "src/agentic_alpha_lab/data/__init__.py",
    "src/agentic_alpha_lab/data/flow_features.py",
    "scripts/opencode_r6m_bigmodel_features.py",
    "scripts/opencode_r9m_nextarch_features.py",
    "scripts/opencode_r9m_nextarch_model.py",
    "scripts/opencode_r48m_attndistill_features.py",
    "scripts/opencode_r48m_attndistill_model.py",
    "scripts/opencode_r48m_attndistill_train.py",
]

KERNEL_TRAIN = '''"""Private free T4x2 orchestration. Two independent research workers, not DDP."""
import torch
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
import zipfile


ARCHIVE = "ARCHIVE_PLACEHOLDER"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _input_tree(input_root, max_entries=200):
    seen = []
    for path in sorted(input_root.rglob("*")):
        if len(seen) >= max_entries:
            break
        try:
            rel = path.relative_to(input_root)
        except ValueError:
            continue
        seen.append(str(rel) + ("/" if path.is_dir() else ""))
    return seen


def unpack(input_root):
    archives = list(input_root.rglob(ARCHIVE))
    if len(archives) == 1:
        bundle = Path(tempfile.mkdtemp(prefix="btc-attndistill-"))
        with zipfile.ZipFile(archives[0]) as z:
            for entry in z.infolist():
                if not (bundle / entry.filename).resolve().is_relative_to(bundle.resolve()):
                    raise ValueError("Unsafe ZIP path")
            z.extractall(bundle)
    elif not archives:
        manifests = [p for p in input_root.rglob("bundle-hashes.json") if p.is_file()]
        if len(manifests) != 1:
            raise ValueError(
                "Expected exactly one private bundle: found 0 archives and %d hash manifests; input tree: %s"
                % (len(manifests), _input_tree(input_root))
            )
        bundle = manifests[0].parent
    else:
        raise ValueError(
            "Ambiguous attached archive: found %d archives; input tree: %s"
            % (len(archives), _input_tree(input_root))
        )
    hashes = json.loads((bundle / "bundle-hashes.json").read_text())
    for name, expected in hashes.items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()) or path.is_symlink() or sha(path) != expected:
            raise ValueError(f"Invalid bundle member: {name}")
    return bundle


def main():
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    print(json.dumps({"allocated_gpus": names, "torch": torch.__version__}), flush=True)
    if len(names) != 2 or not all("T4" in name for name in names):
        warnings.warn(
            "GPU khac ky vong T4x2 (nhan %s) — warn-and-continue, KHONG raise (bai hoc A2 P100 sm_60). "
            "Driver tu chon device kha dung." % (names,)
        )
    bundle = unpack(Path("/kaggle/input"))
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "safetensors==0.6.2", "pyarrow>=18,<24"], check=True)
    allowed = {"distill_attn_v132"}
    found = {}
    for p in (bundle / "configs").glob("*.json"):
        try:
            fam = json.loads(p.read_text()).get("model_family")
        except Exception:
            fam = "<unreadable>"
        found[p.name] = fam
    plans = [p for p in (bundle / "configs").glob("*.json")
             if json.loads(p.read_text()).get("model_family") in allowed]
    if len(plans) != 1:
        raise ValueError(
            "Expected exactly one registered attndistill plan: matched %d (allowed=%s, found=%s)"
            % (len(plans), sorted(allowed), found)
        )
    plan_path = plans[0]
    plan = json.loads(plan_path.read_text())
    parent = json.loads((bundle / plan["folds"]["parent"]).read_text())
    output = Path("/kaggle/working/attndistill-training")
    output.mkdir(exist_ok=False)
    for source, name in ((plan_path, "plan.json"), (bundle / "bundle-hashes.json", "bundle-hashes.json")):
        shutil.copy2(source, output / name)
    shutil.copytree(bundle / "src", output / "source/src")
    shutil.copytree(bundle / "scripts", output / "source/scripts")
    shutil.copytree(bundle / "configs", output / "source/configs")
    (output / "runtime.json").write_text(json.dumps({"gpus": names, "torch": torch.__version__,
        "mode": "independent fold/seed workers", "backtest_location": "local", "live_approved": False}, indent=2))
    workers = []
    driver = plan.get("cloud_driver", "scripts/opencode_r48m_attndistill_train.py")
    if driver != "scripts/opencode_r48m_attndistill_train.py":
        raise ValueError("Unknown cloud driver")
    for shard in range(2):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(shard), PYTHONPATH=str(bundle / "src") + ":" + str(bundle / "scripts"),
                   PYTHONUNBUFFERED="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        workers.append(subprocess.Popen([sys.executable, str(bundle / driver),
            "--plan", str(plan_path), "--output", str(output), "--shard", str(shard)], cwd=bundle, env=env))
    started = time.monotonic()
    guard = int(plan.get("budget", {}).get("guard_wall_seconds", 10800))
    while any(w.poll() is None for w in workers):
        if any(w.poll() not in (None, 0) for w in workers) or time.monotonic() - started > guard:
            for w in workers:
                if w.poll() is None:
                    w.terminate()
            break
        time.sleep(5)
    codes = [w.wait() for w in workers]
    reports, missing = {}, []
    for seed in plan["seeds"]:
        for fold in range(len(parent["folds"])):
            meta = output / f"seed{seed}/checkpoints/fold_{fold}/metadata.json"
            if not meta.exists() or json.loads(meta.read_text())["state"] != "complete":
                missing.append([seed, fold])
            else:
                m = json.loads(meta.read_text())
                val_pred = output / f"seed{seed}/temporal_neural/fold_{fold}/val_predictions_logits.npy"
                if (not val_pred.exists() or "val_prediction_sha256" not in m
                        or "entropy" not in json.dumps(m)):
                    missing.append([seed, fold])
        reports[str(seed)] = {"dataset_manifest_sha256": sha(bundle / plan["dataset"] / "manifest.json"),
                              "plan": parent, "advance_to_further_research": False}
    result = {"state": "complete" if not missing and codes == [0, 0] else "incomplete",
              "plan": plan, "reports": reports, "worker_exit_codes": codes, "missing_or_failed": missing,
              "local_replay_required": True, "portfolio_evaluation": "not_run", "independent_test": False,
              "live_approved": False}
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    if result["state"] != "complete":
        raise RuntimeError("Training incomplete; checkpoints retained, do not evaluate a selected subset")


if __name__ == "__main__":
    main()
'''.replace("ARCHIVE_PLACEHOLDER", ARCHIVE)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    plan = json.loads((ROOT / "configs/opencode_v132_attndistill.json").read_text(encoding="utf-8"))
    assert plan["model_family"] == "distill_attn_v132"
    assert plan["data_frozen"]["total_flat"] == 133
    assert int(plan["training"]["epochs"]) == 12, "v132 FIXED 12"
    assert float(plan["training"]["kl_weight"]) == 1.0, "kl_weight phai 1.0"
    assert float(plan["training"]["ranking_weight_lambda"]) == 0.1, "lambda_rank phai 0.1 THAP"
    assert float(plan["training"]["entropy_lambda"]) == 1.0, "entropy_lambda phai 1.0"
    assert float(plan["training"]["entropy_floor_nats"]) == 2.2, "entropy floor phai 2.2"
    assert (plan["training"]["d_model"], plan["training"]["nhead"], plan["training"]["ff_dim"],
            plan["training"]["frame_layers"], plan["training"]["cross_layers"]) == (128, 4, 256, 2, 1)
    assert plan["epoch_selection"]["mode"].startswith("FIXED"), "v132 bo early-stop"
    assert float(plan["budget"]["gpu_hours_max"]) <= 6.0, "budget tran 6 GPU-gio"
    assert plan["soft_targets_frozen"]["bytes_sha256"] == SOFT_SHA
    assert plan["tie_break"]["eps"] == 1e-06
    assert "val_predictions_logits" in json.dumps(plan["export_spec"]), "thieu val-logits export spec"
    assert sha(ROOT / SOFT_FILE) == SOFT_SHA, "frozen soft-targets bytes khong khop distill artifact"
    out = ROOT / "artifacts/kaggle/opencode_trackM_v132"
    if out.exists():
        raise FileExistsError("Chon staging moi; khong ghi de (xoa tay neu can dong goi lai)")
    (out / "dataset").mkdir(parents=True)
    (out / "kernel").mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="attndistill-bundle-") as tmp:
        stage = Path(tmp) / "bundle"
        hashes = {}
        for name in BUNDLE_MEMBERS:
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
        zpath = out / "dataset" / ARCHIVE
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in sorted(hashes) + ["bundle-hashes.json"]:
                z.write(stage / name, name)
    (out / "dataset" / "dataset-metadata.json").write_text(json.dumps({
        "id": f"{OWNER}/{DATASET_SLUG}", "title": DATASET_SLUG.replace("-", " "),
        "licenses": [{"name": "other"}],
        "description": "Private BTC research snapshot + allowlisted attention-distill (small-Transformer v132) code + FROZEN v38 soft-targets (bytes-identical distill artifact). No credentials. Opened development periods only."},
        indent=2))
    (out / "kernel" / "train.py").write_text(KERNEL_TRAIN, encoding="utf-8")
    (out / "kernel" / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{OWNER}/{KERNEL_SLUG}", "title": KERNEL_SLUG,
        "code_file": "train.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [f"{OWNER}/{DATASET_SLUG}"],
        "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=2))
    manifest = {"owner": OWNER, "dataset_slug": DATASET_SLUG, "kernel_slug": KERNEL_SLUG,
                "archive_sha256": sha(out / "dataset" / ARCHIVE),
                "archive_bytes": (out / "dataset" / ARCHIVE).stat().st_size,
                "files": hashes, "private_required": True,
                "plan": "configs/opencode_v132_attndistill.json",
                "model_family": "distill_attn_v132",
                "architecture": {"kind": "Small-Transformer-encoder pre-norm (cheap attention-distill)",
                                 "d_model": 128, "nhead": 4, "ff_dim": 256,
                                 "frame_layers": 2, "cross_layers": 1,
                                 "band": "<=2M (MUCH cheaper than v96 8.77M)"},
                "loss": {"kl_weight": 1.0, "kl_temperature": 1.0,
                         "entropy_lambda": 1.0, "entropy_floor_nats": 2.2,
                         "ranking_weight_lambda": 0.1, "ranking_kind": "ListNet-on-hard THAP",
                         "ranking_temp": 1.0,
                         "coverage_lambda": 3.0, "coverage_floor": 5e-4},
                "frozen_soft": {"file": SOFT_FILE, "sha256": SOFT_SHA, "shape": [4076, 16]},
                "tie_break": {"eps": 1e-06, "rule": "gap<1e-6 -> holding-asc, index-min (tren LOGITS; bo fill-desc)"},
                "export_spec": {"test": "predictions_logits.npy (n,16) free units",
                                "val": "val_predictions_logits.npy (n,16) free units",
                                "indices": "train/validation/test + soft_rows.json + entropy_stats.json"},
                "epochs": "FIXED 12 (no early-stop)",
                "budget": "33 jobs x FIXED 12ep x ~0.6M + val-logits export, guard 10800s (~6 GPU-h), tran 6 GPU-h",
                "submit_status": "STAGED-ONLY (worker submit rieng sau khi (a) NO RUNNING/QUEUED EITHER ACCOUNT VA (b) student v106 terminal; v132 queue sau student)",
                "submit_command_later": [
                    f"kaggle datasets create -p {out / 'dataset'} --public false",
                    f"kaggle kernels push -p {out / 'kernel'}"],
                "live_approved": False}
    (out / "package-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"staged": str(out), "archive_bytes": manifest["archive_bytes"],
                      "archive_sha256": manifest["archive_sha256"], "n_files": len(hashes),
                      "frozen_soft_sha256": SOFT_SHA,
                      "submit": "KHONG (staged-only, worker submit rieng)"}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force-fresh", action="store_true")
    a = p.parse_args()
    if a.force_fresh:
        shutil.rmtree(ROOT / "artifacts/kaggle/opencode_trackM_v132", ignore_errors=True)
    main(a)
