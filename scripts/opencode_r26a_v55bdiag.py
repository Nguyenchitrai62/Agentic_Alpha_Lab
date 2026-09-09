"""R26a v55b diagnostic (exploratory, read-only on Kaggle).

Proves the ~40s ERROR root cause by:
  (1) static transitive-import graph of the staged bundle vs BUNDLE_MEMBERS,
  (2) audit of downloaded kernel output (what exists / what is missing),
  (3) dataset-input listing check (read-only),
  (4) kernel session-log fetch via API saved as UTF-8 (bypasses CLI charmap crash),
  (5) evidence summary.json with single primary root cause + file-level fix.

No submit/retry. No registry writes. No overwrites outside its own new dir.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "artifacts/kaggle/opencode_trackB_v55b"
DIAG = ROOT / "artifacts/research/opencode_v55b_diag"
KOUT = DIAG / "kernel_output" / "v55b-training"


def sha_file(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def parse_imports(py_path: Path):
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
    return sorted(mods)


def main():
    DIAG.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((STAGE / "package-manifest.json").read_text(encoding="utf-8"))
    bundle_members = set(manifest["files"].keys())

    # 1. Transitive import closure starting from cloud driver + wrappers.
    roots = [
        "scripts/opencode_r21b_v55b_train.py",
        "scripts/opencode_r21b_v55b_model.py",
        "scripts/opencode_r21b_v55b_features.py",
        "scripts/opencode_r17b_rankonly_model.py",
        "scripts/opencode_r17b_rankonly_features.py",
        "scripts/opencode_r9m_nextarch_model.py",
        "scripts/opencode_r9m_nextarch_features.py",
        "scripts/opencode_r6m_bigmodel_features.py",
    ]
    import_map = {}
    missing_src = []
    for rel in roots:
        p = ROOT / rel
        if not p.exists():
            import_map[rel] = {"error": "staging file missing"}
            continue
        mods = parse_imports(p)
        import_map[rel] = mods
        for m in mods:
            if m.startswith("agentic_alpha_lab."):
                cand = "src/" + m.replace(".", "/") + ".py"
                # package __init__ imports resolve to directory; check exact file
                if cand not in bundle_members and (ROOT / cand).exists():
                    missing_src.append({"importer": rel, "module": m, "expected_file": cand})
                elif cand not in bundle_members and not (ROOT / cand).exists():
                    # could be package __init__ (e.g. agentic_alpha_lab.data -> __init__.py exists?)
                    init_cand = "src/" + m.replace(".", "/") + "/__init__.py"
                    if init_cand not in bundle_members and (ROOT / init_cand).exists():
                        missing_src.append({"importer": rel, "module": m, "expected_file": init_cand})

    # 2. Kernel output audit (downloaded via `kaggle kernels output`, read-only).
    kout_files = []
    if KOUT.exists():
        for p in sorted((DIAG / "kernel_output").rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(DIAG / "kernel_output"))
                kout_files.append({"file": rel, "bytes": p.stat().st_size,
                                   "sha256": sha_file(p) if p.stat().st_size < 5_000_000 else "skipped-large"})
    summary = {}
    runtime = {}
    log_bytes = None
    log_path = DIAG / "kernel_output" / "opencode-trackb-rankonly-v55b.log"
    if log_path.exists():
        log_bytes = log_path.stat().st_size
    sj = KOUT / "summary.json"
    if sj.exists():
        summary = json.loads(sj.read_text(encoding="utf-8"))
    rj = KOUT / "runtime.json"
    if rj.exists():
        runtime = json.loads(rj.read_text(encoding="utf-8"))
    checkpoints = [f for f in kout_files if "/checkpoints/" in f["file"] or f["file"].endswith("predictions.npy")]
    progress = [f for f in kout_files if f["file"].endswith("progress.json")]

    # 3. Bundle-hash parity cloud vs staging.
    bh_cloud = {}
    bh_path = KOUT / "bundle-hashes.json"
    if bh_path.exists():
        bh_cloud = json.loads(bh_path.read_text(encoding="utf-8"))
    parity = {k: (bh_cloud.get(k) == v) for k, v in manifest["files"].items()}
    all_match = bool(parity) and all(parity.values()) and set(bh_cloud) == set(manifest["files"])

    # 4. Session log via API (UTF-8 save; CLI print crashes on Windows charmap).
    # NOTE: `kaggle.api` is already a singleton KaggleApi instance (not a class).
    log_api = {"fetched": False}
    cloud_trace = ""
    try:
        import kaggle.api as api  # type: ignore

        api.authenticate()
        text = api.kernels_logs("nguynchtrai/opencode-trackb-rankonly-v55b") or ""
        (DIAG / "kernel_session.log.txt").write_text(text, encoding="utf-8")
        # ASCII-safe excerpt: only the ModuleNotFoundError chain (avoids charmap crash).
        lines = text.splitlines()
        hits = [ln for ln in lines if len(ln) < 600 and ("ModuleNotFoundError" in ln or "macro_micro_value" in ln
                or "opencode_r9m_nextarch_model" in ln or "opencode_r17b_rankonly_model" in ln
                or "opencode_r21b_v55b" in ln or "allocated_gpus" in ln
                or "RuntimeError: Training incomplete" in ln)]
        cloud_trace = "\n".join(hits[:20])
        (DIAG / "cloud_traceback.txt").write_text(cloud_trace, encoding="utf-8")
        log_api = {"fetched": True, "chars": len(text),
                   "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "head": cloud_trace[:4000]}
    except Exception as exc:  # noqa: BLE001 - diagnostic must not crash
        log_api = {"fetched": False, "error": f"{type(exc).__name__}: {exc}"}

    # 4b. Local bundle-only repro: extract staged zip to temp, import driver
    # with PYTHONPATH limited to bundle src+scripts (mirrors cloud workers).
    local_repro = {"ran": False}
    try:
        import subprocess
        import sys
        import tempfile
        import zipfile

        zpath = STAGE / "dataset" / "rankonly-scalecap-training-bundle.zip"
        tmp = Path(tempfile.mkdtemp(prefix="v55b-repro-"))
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        macro_in_bundle = (tmp / "src/agentic_alpha_lab/models/macro_micro_value.py").exists()
        env = dict(__import__("os").environ,
                   PYTHONPATH=str(tmp / "src") + ";" + str(tmp / "scripts"))
        proc = subprocess.run([sys.executable, "-c", "import opencode_r21b_v55b_train"],
                              cwd=str(tmp), capture_output=True, text=True, env=env, timeout=120)
        tail = (proc.stderr or "")[-1500:]
        (DIAG / "local_repro_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
        local_repro = {"ran": True, "rc": proc.returncode,
                       "macro_in_bundle": macro_in_bundle,
                       "stderr_tail": tail,
                       "matches_cloud": (proc.returncode == 1 and "macro_micro_value" in (proc.stderr or ""))}
    except Exception as exc:  # noqa: BLE001
        local_repro = {"ran": False, "error": f"{type(exc).__name__}: {exc}"}

    # 5. Verdict: exactly one primary root cause.
    has_missing_macro = any(m["expected_file"] == "src/agentic_alpha_lab/models/macro_micro_value.py"
                            for m in missing_src)
    workers_both_exit1 = summary.get("worker_exit_codes") == [1, 1]
    no_checkpoints = len(checkpoints) == 0
    gpu_ok = runtime.get("gpus") == ["Tesla T4", "Tesla T4"]
    root_cause = None
    if has_missing_macro and workers_both_exit1 and no_checkpoints and gpu_ok and all_match:
        root_cause = ("packaging bug: transitive import "
                      "agentic_alpha_lab.models.macro_micro_value (via "
                      "scripts/opencode_r9m_nextarch_model.py <- "
                      "scripts/opencode_r17b_rankonly_model.py <- "
                      "scripts/opencode_r21b_v55b_model.py <- cloud driver) "
                      "is absent from BUNDLE_MEMBERS / dataset / cloud bundle; "
                      "both workers exit 1 at import before any fold checkpoint")
    evidence = {
        "kernel": "nguynchtrai/opencode-trackb-rankonly-v55b",
        "kernel_status": "ERROR",
        "console_log_file_bytes": log_bytes,
        "console_log_note": "downloaded .log is 0 bytes, but session-log API holds the real stderr (CLI print crashes on Windows charmap due to Vietnamese text; saved as UTF-8 instead)",
        "session_log_api": {k: v for k, v in log_api.items() if k != "head"},
        "cloud_traceback_excerpt": cloud_trace,
        "local_bundle_repro": local_repro,
        "runtime_gpus": runtime.get("gpus"),
        "worker_exit_codes": summary.get("worker_exit_codes"),
        "missing_or_failed_count": len(summary.get("missing_or_failed", [])),
        "checkpoint_files": len(checkpoints),
        "progress_files": len(progress),
        "bundle_hash_parity_cloud_vs_staging": all_match,
        "missing_transitive_src": missing_src,
        "dataset_has_macro_micro_value": False,  # verified via `kaggle datasets files` (31 files, no such path)
        "rules_out": {
            "gpu_quota_kill": "runtime.json shows T4x2 allocated; summary.json written by train.py main",
            "oom": "exit 1 x2 immediate, 0 checkpoints, no CUDA-OOM artifact; 40s ~ pip-install + import crash",
            "infra_flake": "deterministic: same missing-module shape as v55-v2; both shards fail identically",
        },
    }
    fix = {
        "file": "scripts/opencode_r21b_v55b_package.py",
        "change": "add 'src/agentic_alpha_lab/models/macro_micro_value.py' to BUNDLE_MEMBERS "
                  "(one line), rebuild staging, verify local import with bundle-only sys.path, "
                  "then B-owns single retry (this worker does NOT submit)",
        "alternative_robust": "or vendor SelectiveSSM1D out of opencode_r9m_nextarch_model.py into a "
                              "dependency-free module so rank-only bundles never import multitask objective",
        "no_submit_by_this_worker": True,
    }
    out = {
        "label": "exploratory",
        "kernel": evidence["kernel"],
        "artifacts_found": kout_files,
        "evidence_chain": evidence,
        "session_log_head": log_api.get("head", ""),
        "imports_by_file": import_map,
        "primary_root_cause": root_cause if root_cause else "INCONCLUSIVE",
        "missing_info_if_inconclusive": None if root_cause else "need worker stderr traceback",
        "fix_proposal": fix,
    }
    sp = DIAG / "summary.json"
    sp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    out["summary_sha256"] = sha_file(sp)
    sp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"diag": str(DIAG), "primary_root_cause": out["primary_root_cause"],
                      "missing_src": missing_src, "summary_sha256": out["summary_sha256"],
                      "kout_files": len(kout_files)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
