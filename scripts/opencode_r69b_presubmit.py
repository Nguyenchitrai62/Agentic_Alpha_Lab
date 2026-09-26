"""Opencode R69-B pre-submit audit runner (B-BREAKTHROUGH QA duty).

Reusable checklist runner for Kaggle PRIVATE dataset+kernel stagings.
Audit-only: never submits, never touches credentials, never prints secrets.

Staging contract (built by M packagers, e.g. scripts/opencode_r56m_regime_package.py):
  <staging>/
    dataset/<bundle>.zip + dataset-metadata.json
    kernel/train.py + kernel-metadata.json
    package-manifest.json  (archive_sha256, files{path:sha256}, model_family, ...)

Checks (each PASS/FAIL):
  manifest_hash  - zip sha256 + per-file hashes vs manifest (+ inner bundle-hashes.json)
  secret_scan    - marker scan over bundle .py/.json + metadata + train.py (no secrets in logs)
  gpu_guard      - warn-and-continue present in kernel train.py, no raise-on-mismatch (A2 lesson)
  allowlist      - train.py allowed{} covers manifest/config model_family + exactly-one-plan gate (v33)
  import_test    - bundle-only import test in temp dir: AST local-import resolution for ALL
                   bundle .py + live driver import with PYTHONPATH=temp-only (v55/v55b/v106 lesson)
  layout         - exactly 1 zip (v28 lesson) + 2-branch unpack in train.py + manifest file count
  metadata       - PRIVATE + dataset_sources==[owner/dataset] + slugs match manifest
  prespec        - config arch/loss/export/budget/queue fixed BEFORE packaging (mtime evidence)
  lane           - leader-provided --lane-evidence: no RUNNING/QUEUED on EITHER account

Verdict: SUBMIT-READY (all PASS) | BLOCKED (any FAIL + fix list, M owns fixes+submits)
         PREP-READY (staging absent: nothing to audit yet)

Usage:
  .venv/Scripts/python.exe scripts/opencode_r69b_presubmit.py --staging artifacts/kaggle/<track>
      [--config configs/<plan>.json] [--lane-evidence <json>] --out artifacts/research/<ver>_presubmit

Stdlib only (runs anywhere, no torch/pandas import).
PowerShell: chain with `; if ($?) {}`.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SECRET_MARKERS = (
    b"KAGGLE_API_TOKEN",
    b"KAGGLE_KEY",
    b"kaggle.json",
    b"api_key",
    b"BEGIN PRIVATE KEY",
    b"aws_secret_access_key",
)
SCAN_SUFFIXES = {".py", ".json", ".txt", ".md", ".yaml", ".yml", ".toml", ".cfg", ".env", ".sh"}

# Third-party modules known preinstalled on Kaggle GPU images (no pip line needed).
KAGGLE_PREINSTALLED = {
    "numpy", "pandas", "scipy", "sklearn", "torch", "pyarrow", "safetensors",
    "matplotlib", "tqdm", "requests", "yaml", "PIL", "cv2",
}

REQUIRED_PRESPEC_KEYS = [
    "model_family", "training", "export_spec", "budget", "queue", "cloud", "seeds",
]
REQUIRED_BUDGET_KEYS = ["gpu_hours_max", "guard_wall_seconds", "epochs_fixed", "seeds_fold_jobs"]
REQUIRED_CLOUD_KEYS = ["kernel_slug_suggestion", "dataset_slug_suggestion", "submit_rule"]

FIXES = {
    "staging_present": "M: (re)run the packager; expected <staging>/dataset/*.zip + kernel/train.py + package-manifest.json.",
    "manifest_hash": "M: rebuild staging (hashes stale after edit). Do NOT hand-edit the zip; rerun packager fresh.",
    "secret_scan": "M: remove the flagged marker/secret from source, rebuild staging, re-run audit. Rotate any exposed token.",
    "gpu_guard": "M: add warn-and-continue GPU guard in kernel train.py (warnings.warn + KHONG raise, no raise on T4-mismatch). See v145 KERNEL_TRAIN.",
    "allowlist": "M: add the model_family to train.py allowed{} AND ensure exactly-one-plan gate matches bundle configs (v33 lesson).",
    "import_test": "M: add the missing local module to BUNDLE_MEMBERS in the packager, rebuild, re-run audit (v55/v55b/v106 lesson).",
    "layout": "M: stage exactly ONE dataset zip (v28 lesson: extracted-upload breaks unpack). Keep 2-branch unpack in train.py.",
    "metadata": "M: fix kernel/dataset metadata (is_private=true, dataset_sources=[owner/dataset_slug], slugs match manifest, --public false).",
    "prespec": "M: freeze arch/loss/export/budget/queue in the config BEFORE packaging; do not edit config after staging (mtime evidence).",
    "lane": "Leader: confirm no RUNNING/QUEUED on EITHER Kaggle account (read-only status check, opaque tokens), pass --lane-evidence JSON.",
}


def sha_file(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def result(name, ok, detail):
    return {"check": name, "result": "PASS" if ok else "FAIL", "detail": detail}


def check_staging(staging):
    staging = Path(staging)
    manifest = staging / "package-manifest.json"
    zips = sorted((staging / "dataset").glob("*.zip")) if (staging / "dataset").is_dir() else []
    train = staging / "kernel" / "train.py"
    missing = [str(p) for p in (manifest, train) if not p.exists()]
    if not staging.is_dir():
        return result("staging_present", False, f"absent: {staging}"), None
    if missing:
        return result("staging_present", False, f"missing={missing}"), None
    ctx = {"staging": staging, "manifest_path": manifest, "zip": zips[0] if len(zips) == 1 else None,
           "zips": zips, "train": train}
    if len(zips) != 1:
        return result("staging_present", False, f"manifest+train.py present but {len(zips)} zip(s) (see layout)"), ctx
    return result("staging_present", True, f"manifest+train.py+{len(zips)} zip(s)"), ctx


def check_manifest_hash(ctx):
    try:
        manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    except Exception as exc:
        return result("manifest_hash", False, f"manifest unreadable: {exc}")
    if ctx["zip"] is None:
        return result("manifest_hash", False, "no single zip to hash (see layout)")
    actual_archive = sha_file(ctx["zip"])
    problems = []
    if actual_archive != manifest.get("archive_sha256"):
        problems.append("archive_sha256 mismatch")
    if ctx["zip"].stat().st_size != manifest.get("archive_bytes"):
        problems.append("archive_bytes mismatch")
    try:
        with zipfile.ZipFile(ctx["zip"]) as zf:
            members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    except Exception as exc:
        return result("manifest_hash", False, f"zip unreadable: {exc}")
    inner = {}
    if "bundle-hashes.json" in members:
        try:
            inner = json.loads(members["bundle-hashes.json"].decode("utf-8"))
        except Exception as exc:
            problems.append(f"bundle-hashes.json unreadable: {exc}")
    files = manifest.get("files", {})
    if set(members) - {"bundle-hashes.json"} != set(files):
        problems.append(f"member set != manifest files (zip={len(members)-1} manifest={len(files)})")
    for name, expected in files.items():
        if name in members and hashlib.sha256(members[name]).hexdigest() != expected:
            problems.append(f"hash mismatch: {name}")
    if inner and (set(inner) != set(files) or any(inner.get(k) != v for k, v in files.items())):
        problems.append("bundle-hashes.json != manifest files")
    detail = f"{len(files)} files verified, archive {actual_archive[:12]}..." if not problems else "; ".join(problems)
    return result("manifest_hash", not problems, detail)


def check_secret_scan(ctx):
    hits = []

    def scan_bytes(blob, label):
        for marker in SECRET_MARKERS:
            if marker in blob:
                hits.append(f"{label}:{marker.decode()}")
                break  # one hit per file is enough; never dump content

    try:
        with zipfile.ZipFile(ctx["zip"]) as zf:
            for name in zf.namelist():
                if name.endswith("/") or Path(name).suffix not in SCAN_SUFFIXES:
                    continue
                scan_bytes(zf.read(name), f"bundle:{name}")
    except Exception as exc:
        return result("secret_scan", False, f"zip unreadable: {exc}")
    for extra in ("dataset/dataset-metadata.json", "kernel/kernel-metadata.json", "kernel/train.py"):
        p = ctx["staging"] / extra
        if p.exists():
            scan_bytes(p.read_bytes(), extra)
    return result("secret_scan", not hits, "clean" if not hits else f"markers in {hits}")


def check_gpu_guard(ctx):
    src = ctx["train"].read_text(encoding="utf-8")
    has_warn = "warnings.warn" in src
    has_no_raise_note = ("KHONG raise" in src) or ("warn-and-continue" in src.lower())
    raise_near_gpu = bool(re.search(r"(?i)(cuda|get_device_name|sm_60|Tesla|T4.{0,80}raise|raise.{0,80}(gpu|cuda|device))", src)
                          and re.search(r"^\s*raise\s+\w+", src, re.M))
    if not has_warn:
        return result("gpu_guard", False, "kernel train.py lacks warnings.warn GPU guard (A2 P100 lesson)")
    if not has_no_raise_note:
        return result("gpu_guard", False, "guard present but no warn-and-continue intent marker")
    if raise_near_gpu and "KHONG raise" not in src:
        return result("gpu_guard", False, "bare raise near GPU check (must warn-and-continue, never self-destruct)")
    return result("gpu_guard", True, "warn-and-continue guard present, no raise-on-mismatch")


def _allowed_families(train_src):
    try:
        tree = ast.parse(train_src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "allowed" for t in node.targets):
            val = node.value
            if isinstance(val, (ast.Set, ast.List, ast.Tuple)):
                fams = {e.value for e in val.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                if fams:
                    return fams
    return set()


def _local_module_index(bundle_root):
    """Map importable local names -> relative path inside bundle."""
    index = {}
    for base, prefix in (("src", ""), ("scripts", "")):
        root = bundle_root / base
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            rel = py.relative_to(root)
            parts = list(rel.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            if not parts:
                continue
            if base == "src":
                dotted = ".".join(parts)
            else:
                dotted = parts[-1] if len(parts) == 1 else ".".join(parts)
                index[dotted] = str(py.relative_to(bundle_root))
                continue
            index[dotted] = str(py.relative_to(bundle_root))
    return index


def _declared_third_party(train_src):
    deps = set(KAGGLE_PREINSTALLED)
    for m in re.finditer(r"pip\s+install[^\n]*", train_src):
        for tok in re.split(r"[ ,\"']+", m.group(0)):
            pkg = re.split(r"[=<>!;]", tok)[0].strip().lower().replace("-", "_")
            if pkg and pkg not in ("pip", "install", "python", "m", "disable", "check"):
                deps.add(pkg)
    return deps


def check_allowlist_and_imports(ctx, config_path):
    train_src = ctx["train"].read_text(encoding="utf-8")
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest_family = manifest.get("model_family", "")
    allowed = _allowed_families(train_src)
    gate_ok = "Expected exactly one registered" in train_src or "Expected exactly one private bundle" in train_src
    cfg_family = ""
    if config_path and Path(config_path).exists():
        try:
            cfg_family = json.loads(Path(config_path).read_text(encoding="utf-8")).get("model_family", "")
        except Exception:
            cfg_family = "<unreadable>"
    problems = []
    if not allowed:
        problems.append("no allowed{} set parsed in train.py (v33 filter-plan lesson)")
    else:
        if manifest_family and manifest_family not in allowed:
            problems.append(f"manifest family {manifest_family!r} not in allowed={sorted(allowed)}")
        if cfg_family and cfg_family not in allowed:
            problems.append(f"config family {cfg_family!r} not in allowed={sorted(allowed)}")
    if not gate_ok:
        problems.append("exactly-one-plan/bundle gate missing in train.py")
    allow_res = result("allowlist", not problems,
                       f"allowed={sorted(allowed)} family={manifest_family!r}" if not problems else "; ".join(problems))

    # ---- bundle-only import test in temp dir (THE v55-catcher) ----
    tmp = Path(tempfile.mkdtemp(prefix="presubmit-"))
    try:
        if ctx["zip"] is None:
            return allow_res, result("import_test", False, "no single zip to extract (see layout)")
        with zipfile.ZipFile(ctx["zip"]) as zf:
            zf.extractall(tmp)
        py_files = [p for p in tmp.rglob("*.py") if "__pycache__" not in p.parts]
        for p in py_files:  # syntax proof first
            try:
                compile(p.read_bytes(), str(p), "exec")
            except SyntaxError as exc:
                return allow_res, result("import_test", False, f"syntax error in bundle {p.relative_to(tmp)}: {exc}")
        index = _local_module_index(tmp)
        declared = _declared_third_party(train_src)
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        missing_local, unknown_third = set(), set()
        importers = {}
        for p in py_files:
            try:
                tree = ast.parse(p.read_bytes())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                    full = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        names, full = ["<relative>"], ["<relative>"]
                    else:
                        mod = (node.module or "").split(".")[0]
                        names, full = [mod], [(node.module or "")]
                else:
                    continue
                for short, dotted in zip(names, full):
                    if short == "<relative>":
                        continue
                    if short in stdlib or short in declared or short in index or dotted in index:
                        continue
                    if short in sys.builtin_module_names:
                        continue
                    top_hit = any(k == short or k.startswith(short + ".") for k in index)
                    if top_hit:
                        continue
                    try:
                        __import__(short)
                    except Exception:
                        missing_local.add(short)
                        importers.setdefault(short, set()).add(str(p.relative_to(tmp)))
                    else:
                        unknown_third.add(short)
        # A missing LOCAL module (in-bundle import graph, not installed here) is the v55 death.
        fatal = sorted(m for m in missing_local if m.startswith(("agentic_alpha_lab", "opencode_")) or m in index)
        if fatal:
            detail = "; ".join(f"{m} (needed by {sorted(importers[m])[0]})" for m in fatal)
            import_res = result("import_test", False, f"missing bundle-local module(s): {detail}")
            return allow_res, import_res
        # Live driver import with PYTHONPATH=temp-only (no repo leakage).
        drivers = _find_drivers(tmp, config_path)
        if not drivers:
            return allow_res, result("import_test", False, "no cloud driver (*_train.py) found in bundle scripts/")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp / "src"), str(tmp / "scripts")]))
        live_problems = []
        for drv in drivers:
            cmd = [sys.executable, "-c", f"import torch; import {drv}; print('IMPORT-OK {drv}')"]
            try:
                proc = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                live_problems.append(f"{drv}: import timeout (>300s, side effects at import?)")
                continue
            if proc.returncode != 0:
                err = (proc.stderr or "")[-1500:]
                m = re.search(r"ModuleNotFoundError: No module named '([\w.]+)'", err)
                if m and (m.group(1).split(".")[0] in ("agentic_alpha_lab",) or m.group(1) in index
                          or m.group(1).split(".")[0].startswith("opencode_")):
                    return allow_res, result("import_test", False, f"live import {drv}: missing {m.group(1)}")
                live_problems.append(f"{drv}: exit {proc.returncode}: {err[-300:]}")
        if live_problems:
            return allow_res, result("import_test", False, " | ".join(live_problems))
        warn = f"; third-party-only-here-not-declared={sorted(unknown_third)}" if unknown_third else ""
        return allow_res, result("import_test", True, f"AST+live OK drivers={drivers}{warn}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _find_drivers(bundle_tmp, config_path):
    if config_path and Path(config_path).exists():
        try:
            drv = json.loads(Path(config_path).read_text(encoding="utf-8")).get("cloud_driver", "")
            if drv.endswith(".py"):
                stem = Path(drv).stem
                if (bundle_tmp / drv).exists():
                    return [stem]
        except Exception:
            pass
    scripts = bundle_tmp / "scripts"
    if scripts.is_dir():
        return sorted(p.stem for p in scripts.glob("*_train.py"))
    return []


def check_layout(ctx):
    train_src = ctx["train"].read_text(encoding="utf-8")
    n_zip = len(ctx["zips"])
    two_branch = ("rglob(ARCHIVE)" in train_src or "rglob(" in train_src) and ("bundle-hashes.json" in train_src)
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    if n_zip == 0:
        return result("layout", False, "0 zip in dataset/ (v28 lesson: upload EXTRACTED breaks unpack; stage exactly one zip)")
    if n_zip > 1:
        return result("layout", False, f"{n_zip} zips (ambiguous attach; keep exactly one)")
    if not two_branch:
        return result("layout", False, "train.py lacks 2-branch unpack (zip + extracted fallback with bundle-hashes.json)")
    with zipfile.ZipFile(ctx["zip"]) as zf:
        n_members = sum(1 for n in zf.namelist() if not n.endswith("/")) - 1  # minus bundle-hashes.json
    if n_members != len(manifest.get("files", {})):
        return result("layout", False, f"zip members {n_members} != manifest files {len(manifest.get('files', {}))}")
    return result("layout", True, f"1 zip + 2-branch unpack + {n_members} members match manifest")


def check_metadata(ctx):
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    owner, ds_slug, k_slug = manifest.get("owner"), manifest.get("dataset_slug"), manifest.get("kernel_slug")
    problems = []
    try:
        ds_meta = json.loads((ctx["staging"] / "dataset" / "dataset-metadata.json").read_text(encoding="utf-8"))
        k_meta = json.loads((ctx["staging"] / "kernel" / "kernel-metadata.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return result("metadata", False, f"metadata unreadable: {exc}")
    if ds_meta.get("id") != f"{owner}/{ds_slug}":
        problems.append(f"dataset id {ds_meta.get('id')!r} != {owner}/{ds_slug}")
    if k_meta.get("id") != f"{owner}/{k_slug}":
        problems.append(f"kernel id {k_meta.get('id')!r} != {owner}/{k_slug}")
    if k_meta.get("is_private") is not True:
        problems.append("kernel is_private != true")
    if k_meta.get("dataset_sources") != [f"{owner}/{ds_slug}"]:
        problems.append(f"dataset_sources {k_meta.get('dataset_sources')!r} != ['{owner}/{ds_slug}']")
    if manifest.get("private_required") is not True:
        problems.append("manifest private_required != true")
    cmds = " ".join(manifest.get("submit_command_later", []))
    if "--public false" not in cmds and "--public=False" not in cmds:
        problems.append("submit commands lack --public false")
    return result("metadata", not problems, "PRIVATE + sources + slugs OK" if not problems else "; ".join(problems))


def check_prespec(ctx, config_path):
    if not config_path:
        plan = json.loads(ctx["manifest_path"].read_text(encoding="utf-8")).get("plan", "")
        auto = ctx["staging"] / ".." / plan
        auto = (Path(ctx["staging"]).parents[1] / plan) if plan else None
        if auto is not None and auto.exists():
            config_path = str(auto)
        else:
            return result("prespec", False, "no --config given and manifest plan not found locally")
    cfg_p = Path(config_path)
    if not cfg_p.exists():
        return result("prespec", False, f"config absent: {config_path}")
    try:
        cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    except Exception as exc:
        return result("prespec", False, f"config unreadable: {exc}")
    problems = [f"missing key: {k}" for k in REQUIRED_PRESPEC_KEYS if k not in cfg]
    for k in REQUIRED_BUDGET_KEYS:
        if k not in cfg.get("budget", {}):
            problems.append(f"missing budget.{k}")
    for k in REQUIRED_CLOUD_KEYS:
        if k not in cfg.get("cloud", {}):
            problems.append(f"missing cloud.{k}")
    try:
        frozen_before = cfg_p.stat().st_mtime <= ctx["manifest_path"].stat().st_mtime + 60
    except OSError:
        frozen_before = False
    if not frozen_before:
        problems.append("config mtime NEWER than package-manifest (edited after packaging; re-freeze + rebuild)")
    return result("prespec", not problems,
                  f"{cfg.get('model_family')} fixed pre-package" if not problems else "; ".join(problems))


def check_lane(evidence_path):
    if not evidence_path or not Path(evidence_path).exists():
        return {"check": "lane", "result": "NOT-VERIFIED",
                "detail": "no --lane-evidence (leader must confirm no RUNNING/QUEUED on EITHER account)"}
    try:
        ev = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"check": "lane", "result": "FAIL", "detail": f"lane evidence unreadable: {exc}"}
    busy = {a: s for a, s in ev.get("accounts", {}).items() if str(s).upper() in ("RUNNING", "QUEUED", "SUBSCRIBED")}
    if busy:
        return {"check": "lane", "result": "FAIL", "detail": f"lane busy: {busy} (submit iff lane free)"}
    return {"check": "lane", "result": "PASS", "detail": f"both accounts terminal per {evidence_path}"}


def main():
    ap = argparse.ArgumentParser(description="R69-B pre-submit audit (audit-only, no submits).")
    ap.add_argument("--staging", required=True, help="artifacts/kaggle/<track> dir")
    ap.add_argument("--config", default="", help="frozen plan config (else auto from manifest plan)")
    ap.add_argument("--lane-evidence", default="", help="leader lane-state JSON")
    ap.add_argument("--out", required=True, help="output dir for summary.json")
    args = ap.parse_args()

    checks = []
    st_res, ctx = check_staging(args.staging)
    checks.append(st_res)
    if ctx is None:
        verdict, fixes = "PREP-READY", []
    else:
        checks.append(check_manifest_hash(ctx))
        checks.append(check_secret_scan(ctx))
        checks.append(check_gpu_guard(ctx))
        allow_res, import_res = check_allowlist_and_imports(ctx, args.config or "")
        checks.append(allow_res)
        checks.append(import_res)
        checks.append(check_layout(ctx))
        checks.append(check_metadata(ctx))
        checks.append(check_prespec(ctx, args.config or ""))
        checks.append(check_lane(args.lane_evidence or ""))
        failed = [c for c in checks if c["result"] in ("FAIL", "NOT-VERIFIED")]
        verdict = "SUBMIT-READY" if not failed else "BLOCKED"
        fixes = [f"{c['check']}: {FIXES.get(c['check'], 'investigate')}" for c in failed]

    summary = {"agent": "B-presubmit", "staging": args.staging, "config": args.config or None,
               "verdict": verdict, "checks": checks, "fixes": fixes}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in checks:
        print(f"[{c['result']}] {c['check']}: {c['detail']}")
    print(f"VERDICT: {verdict}")
    if fixes:
        print("FIXES:")
        for f in fixes:
            print(f"  - {f}")
    return 0 if verdict == "SUBMIT-READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
