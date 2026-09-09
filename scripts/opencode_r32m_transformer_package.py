"""Opencode R32-M packager v96: build PRIVATE Kaggle dataset+kernel staging, KHONG submit.

Doc: configs/opencode_v96_transformer.json (dong bang truoc). Output:
  artifacts/kaggle/opencode_trackM_v96/
    dataset/transformer-training-bundle.zip + dataset-metadata.json (PRIVATE)
    kernel/train.py + kernel-metadata.json (PRIVATE T4x2)
    package-manifest.json (sha256, khong secret)
Quy tac: chi staging o day; submit (dataset create + kernels push) do worker
thuc hien RIENG sau khi xac minh (a) lane free tren account-1 VA (b) B-v55c
terminal (v96 queue sau B-v55c). Max ONE submission. Dataset-ready gate + gap >=60s.
Failover CHI tren explicit QUOTA-exhaustion error (ghi nguyen van) -> retry MOT lan
account-2; loi khac -> diagnose, KHONG failover.
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
DATASET_SLUG = "opencode-trackm-transformer-v96-data"
KERNEL_SLUG = "opencode-trackm-transformer-v96"
ARCHIVE = "transformer-training-bundle.zip"

BUNDLE_MEMBERS = [
    "configs/opencode_v96_transformer.json",
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
    "src/agentic_alpha_lab/__init__.py",
    "src/agentic_alpha_lab/models/__init__.py",
    "src/agentic_alpha_lab/models/macro_micro_value.py",
    "src/agentic_alpha_lab/models/ranked_loss.py",
    "src/agentic_alpha_lab/models/temporal_validation.py",
    "src/agentic_alpha_lab/data/__init__.py",
    "src/agentic_alpha_lab/data/flow_features.py",
    "scripts/opencode_r6m_bigmodel_features.py",
    "scripts/opencode_r9m_nextarch_features.py",
    "scripts/opencode_r9m_nextarch_model.py",
    "scripts/opencode_r32m_transformer_features.py",
    "scripts/opencode_r32m_transformer_model.py",
    "scripts/opencode_r32m_transformer_train.py",
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
        bundle = Path(tempfile.mkdtemp(prefix="btc-transformer-"))
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
    allowed = {"transformer_ranklist_v96"}
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
            "Expected exactly one registered transformer plan: matched %d (allowed=%s, found=%s)"
            % (len(plans), sorted(allowed), found)
        )
    plan_path = plans[0]
    plan = json.loads(plan_path.read_text())
    parent = json.loads((bundle / plan["folds"]["parent"]).read_text())
    output = Path("/kaggle/working/transformer-training")
    output.mkdir(exist_ok=False)
    for source, name in ((plan_path, "plan.json"), (bundle / "bundle-hashes.json", "bundle-hashes.json")):
        shutil.copy2(source, output / name)
    shutil.copytree(bundle / "src", output / "source/src")
    shutil.copytree(bundle / "scripts", output / "source/scripts")
    shutil.copytree(bundle / "configs", output / "source/configs")
    (output / "runtime.json").write_text(json.dumps({"gpus": names, "torch": torch.__version__,
        "mode": "independent fold/seed workers", "backtest_location": "local", "live_approved": False}, indent=2))
    workers = []
    driver = plan.get("cloud_driver", "scripts/opencode_r32m_transformer_train.py")
    if driver != "scripts/opencode_r32m_transformer_train.py":
        raise ValueError("Unknown cloud driver")
    for shard in range(2):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(shard), PYTHONPATH=str(bundle / "src") + ":" + str(bundle / "scripts"),
                   PYTHONUNBUFFERED="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        workers.append(subprocess.Popen([sys.executable, str(bundle / driver),
            "--plan", str(plan_path), "--output", str(output), "--shard", str(shard)], cwd=bundle, env=env))
    started = time.monotonic()
    guard = int(plan.get("budget", {}).get("guard_wall_seconds", 21600))
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
                # v96: bat buoc co val-pred RAW + sizing-rieng + value_scale moi duoc coi la complete
                val_pred = output / f"seed{seed}/temporal_neural/fold_{fold}/val_predictions.npy"
                siz_pred = output / f"seed{seed}/temporal_neural/fold_{fold}/predictions_sizing_capped.npy"
                if (not val_pred.exists() or "val_prediction_sha256" not in m
                        or not siz_pred.exists() or "mu_train" not in json.dumps(m)):
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
    plan = json.loads((ROOT / "configs/opencode_v96_transformer.json").read_text(encoding="utf-8"))
    assert plan["model_family"] == "transformer_ranklist_v96"
    assert plan["data_frozen"]["total_flat"] == 133
    assert plan["architecture"]["params_target"]["measured_parameters"] == 8768459, "smoke chua fill params"
    assert int(plan["training"]["epochs"]) == 16, "v96 FIXED 16"
    assert float(plan["training"]["ranking_weight"]) == 2.0, "ranking PRIMARY 2.0"
    assert float(plan["training"]["value_weight"]) == 1.0, "value 1.0"
    assert float(plan["training"]["ranking_weight"]) >= float(plan["training"]["value_weight"]), "ranking>=value"
    assert str(plan["training"]["value_scale_method"]) == "standardize_train_window", "v96 phai chuan-hoa"
    assert float(plan["training"]["sizing_cap_percent"]) == 2.0, "v96 sizing cap phai 2.0 percent"
    assert float(plan["training"]["tie_break_eps"]) == 1e-6, "v96 eps phai 1e-6"
    assert "policy_cap_cap" not in plan["training"] and "policy_cap_mode" not in plan["training"], "v96 khong clip selection"
    assert plan["epoch_selection"]["mode"].startswith("FIXED"), "v96 bo early-stop"
    assert float(plan["budget"]["gpu_hours_max"]) <= 12.0, "budget tran 12 GPU-gio"
    cov = plan["coverage_floor"]
    assert cov["loss_mechanism"]["params"] == {"FLOOR_POS": 0.0005, "LAMBDA_COV": 3.0}
    assert plan["coverage_floor"]["policy_mechanism"]["sizing_cap"]["cap_value"] == 2.0
    assert plan["tie_break"]["eps"] == 1e-06
    assert "val_predictions" in json.dumps(plan["export_spec"]), "thieu val-pred export spec"
    assert "sizing_capped" in json.dumps(plan["export_spec"]), "thieu sizing-rieng export spec"
    assert "xla_tolerable" in json.dumps(plan), "thieu XLA statement"
    assert "causal_masking_note" in json.dumps(plan["architecture"]), "thieu causal-mask note"
    out = ROOT / "artifacts/kaggle/opencode_trackM_v96"
    if out.exists():
        raise FileExistsError("Chon staging moi; khong ghi de (xoa tay neu can dong goi lai)")
    (out / "dataset").mkdir(parents=True)
    (out / "kernel").mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="transformer-bundle-") as tmp:
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
        "description": "Private BTC research snapshot + allowlisted transformer-ranklist (v96, 8.77M) code. No credentials. Opened development periods only."},
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
                "plan": "configs/opencode_v96_transformer.json",
                "model_family": "transformer_ranklist_v96",
                "architecture": {"kind": "Transformer-encoder pre-norm", "d_model": 320,
                                 "nhead": 8, "ff_dim": 1024,
                                 "frame_layers": 5, "cross_layers": 2,
                                 "measured_parameters": 8768459, "band": "8-12M"},
                "loss_weights": {"value": 1.0, "rank_listnet_primary": 2.0, "dir": 1.0, "quant": 1.0,
                                 "exc": 0.5, "cov_lambda": 3.0},
                "ranking_params": {"kind": "ListNet-listwise", "temperature_percent": 1.0},
                "value_scale": {"method": "standardize_train_window", "sigma_floor": 1e-06},
                "selection": {"mode": "select-raw (KHONG CLIP)"},
                "sizing_cap_separate": {"mode": "clip", "cap": 2.0, "unit": "percent",
                                        "applies_to": "sizing copy only"},
                "tie_break": {"eps": 1e-06, "rule": "gap<1e-6 -> fill-desc, holding-asc, index-min"},
                "export_spec": {"test": "predictions.npy (RAW TRADEABLE percent, KHONG CLIP)",
                                "val": "val_predictions.npy (RAW TRADEABLE percent, KHONG CLIP)",
                                "sizing_test": "predictions_sizing_capped.npy (clip +-2.0% RIENG)",
                                "sizing_val": "val_predictions_sizing_capped.npy (clip +-2.0% RIENG)",
                                "indices": "train/validation/test + value_scale.json"},
                "epochs": "FIXED 16 (no early-stop)",
                "coverage_floor": {"lambda": 3.0, "floor_pos": 5e-4, "domain": "TRADEABLE", "n_min_per_fold": 8, "margin": 0.0},
                "calibration": "val-pred RAW export enables REAL calibrate-first local: isotonic outlier-robust past-only TREN VAL + nguong tu phan vi validation",
                "xla": "XLA-tolerable per design review (Linear/LayerNorm/Dropout/softmax/GELU/Embedding only; no recurrence loop, no dynamic shapes); target T4x2, TPU future",
                "causal_masking": "not needed: windows past-only by construction (DOCUMENTED in plan)",
                "budget": "33 jobs x FIXED 16ep x 8.77M + val-export + sizing-copy forward-only, guard 21600s (<=12 GPU-h)",
                "submit_status": "STAGED-ONLY (worker submit rieng sau khi (a) lane free tren account-1 VA (b) B-v55c terminal; v96 queue sau B-v55c)",
                "submit_command_later": [
                    f"kaggle datasets create -p {out / 'dataset'} --public false",
                    f"kaggle kernels push -p {out / 'kernel'}"],
                "live_approved": False}
    (out / "package-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"staged": str(out), "archive_bytes": manifest["archive_bytes"],
                      "archive_sha256": manifest["archive_sha256"], "n_files": len(hashes),
                      "submit": "KHONG (staged-only, worker submit rieng)"}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force-fresh", action="store_true")
    a = p.parse_args()
    if a.force_fresh:
        shutil.rmtree(ROOT / "artifacts/kaggle/opencode_trackM_v96", ignore_errors=True)
    main(a)
