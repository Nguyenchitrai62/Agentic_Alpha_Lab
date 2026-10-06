"""Smoke tests for the generic 4-phase engine Kaggle bundle (ops_kaggleengine).

Covers, without uploads or heavy full runs:
  1. bundle closure resolves (40 files, all exist) and kaggle_entry.py
     extracts back to the same tree (extractor round-trip);
  2. every kernel INPUTS path and MANIFEST file exists locally with the
     listed byte size;
  3. job_example.json reproduces the oc_expiry4p RUNS cfg and the
     bear_expiry hook reproduces oc_expiry4p's halving exactly;
  4. local smoke (ENGINE_SMOKE_*, shift 0, one row, tiny 10-day window):
     kernel_run.main (KAGGLE_INPUT_BASE/KAGGLE_WORKING_BASE wiring) writes
     results.json + runs.pkl byte-identical to the direct harness call on
     the same subset.
  5. outside-repo bundle check: the built kaggle_entry.py BUNDLE extracts
     to a temp dir outside the repo, every closure module loads there with
     a clean sys.path (no repo root), plus a 60-bar ENGINE_SMOKE run from
     the extracted dir (KAGGLE_INPUT_BASE -> artifacts/kaggle_stage).

Run: .venv/Scripts/python.exe -m pytest tests/test_ops_kaggleengine.py -q
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
KERN = ROOT / "artifacts/kaggle_stage/engine_kernel"
sys.path.insert(0, str(KERN))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_closure_and_inputs_exist():
    import build_bundle as B
    files = B.closure(ROOT)
    assert len(files) == 40, f"closure drift: {len(files)} files"
    assert "research/parallel/rounds/parallel-20260906-r2/rl/trader_rl.py" in files  # sys.path import (v214/v215)
    for f in files:
        assert (ROOT / f).exists(), f
    inputs = json.loads((KERN / "INPUTS.json").read_text())["inputs"]
    import kernel_run as KR
    assert KR.INPUTS == inputs
    for rel in inputs:
        assert (ROOT / rel).exists(), rel


def test_manifest_sizes():
    man = json.loads((ROOT / "artifacts/kaggle_stage/engine_data/MANIFEST.json").read_text())
    assert man["total_bytes"] == sum(f["bytes"] for f in man["files"])
    for f in man["files"]:
        p = ROOT / f["path"]
        assert p.exists(), f["path"]
        assert p.stat().st_size == f["bytes"], f["path"]


def test_entry_roundtrip(tmp_path):
    import build_bundle as B  # noqa: F401 -- ensures builder imports cleanly
    src = (KERN / "kaggle_entry.py").read_text()
    b64 = src.split('BUNDLE = "', 1)[1].split('"', 1)[0]
    zipfile.ZipFile(io.BytesIO(base64.b64decode(b64))).extractall(tmp_path)
    assert (tmp_path / "kernel_run.py").exists()
    assert (tmp_path / "engine_harness.py").exists()
    for rel in ("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
                "research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py",
                "research/parallel/rounds/parallel-20260906-r2/rl/trader_rl.py",
                "backend/history_tm.py", "scripts/forward_v205.py"):
        assert (tmp_path / rel).read_bytes() == (ROOT / rel).read_bytes(), rel


def test_job_matches_oc_expiry4p_and_hook_exact():
    job = json.loads((KERN / "job_example.json").read_text())
    oc = _load("oc4p_ref", ROOT / "research/diagnostics/oc_expiry4p/oc_expiry4p.py")
    assert [r["name"] for r in job["rows"]] == list(oc.RUNS)
    base, exp = job["rows"]
    assert base["sleeve"] == {k: v for k, v in oc.RUNS["R2B1D17BFG2"].items()}
    assert base["book_hook"] == "bear"
    assert exp["book_hook"] == "bear_expiry"
    import engine_harness as H
    import hooks as HK
    assert (HK.EXP[["E"]] == oc.EXP[["E"]]).all().all()
    _, _, _, _, _, books154, opens_std, std_books, _ = H.load_books(ROOT)
    sb = std_books.copy()
    bear = H.bear_mask(sb, opens_std)
    assert bear.any() and (~bear).any()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    got = HK.apply("bear_expiry", sb, ROOT)
    want = sb.copy()
    want.loc[oc.in_expiry_window(sb.index, oc.EXP)] *= 0.5
    pd.testing.assert_frame_equal(got, want)


def test_find_and_wire_mini_dataset(tmp_path, monkeypatch):
    import kernel_run as KR
    ds = tmp_path / "input" / "ds"
    (ds / "data/raw/btc_intraday_20260924").mkdir(parents=True)
    (ds / "data/raw/btc_intraday_20260924" / "x.parquet").write_bytes(b"0")
    (ds / "artifacts/research/engine_real").mkdir(parents=True)
    (ds / "artifacts/research/engine_real" / "books_v154.parquet").write_bytes(b"1")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "work").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path / "work")
    root = KR._find_dataset_root(tmp_path / "input")
    assert root == ds
    monkeypatch.setattr(KR, "INPUTS", ["data/raw/btc_intraday_20260924",
                                        "artifacts/research/engine_real/books_v154.parquet"])
    KR._wire_dataset(root)
    assert Path("data/raw/btc_intraday_20260924").exists()
    assert Path("artifacts/research/engine_real/books_v154.parquet").exists()


def test_smoke_kernel_matches_direct(tmp_path, monkeypatch):
    import engine_harness as H
    import kernel_run as KR
    job = {"name": "smoke", "rows": [{"name": "BASE",
                                      "book_hook": "bear",
                                      "sleeve": {"rule": "inv", "k": 1.0, "kd": 1.7, "bear": True, "G": 2.0}}]}
    env = {"REPO_ROOT": str(ROOT), "KAGGLE_INPUT_BASE": str(ROOT),
           "ENGINE_SHIFTS": "0", "ENGINE_SMOKE_START": "2024-03-01",
           "ENGINE_SMOKE_BARS": "60", "ENGINE_NO_SCORE": "1"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    jp = tmp_path / "job.json"
    jp.write_text(json.dumps(job))
    direct = tmp_path / "direct"
    res = H.run_rows(job, direct, ROOT)
    assert (direct / "results.json").exists() and (direct / "runs.pkl").exists()
    assert res["rows"]["BASE"]["bars"] == {0: 60}
    out_base = tmp_path / "kwork"
    monkeypatch.setenv("KAGGLE_WORKING_BASE", str(out_base))
    monkeypatch.chdir(tmp_path)
    assert KR.main(["--job", str(jp)]) == 0
    out = out_base / "out_eng"
    a = json.loads((out / "results.json").read_text())
    b = json.loads((direct / "results.json").read_text())
    a.pop("seconds", None)
    b.pop("seconds", None)
    assert a == b  # kernel path reproduces the direct harness call exactly
    assert (out / "runs.pkl").read_bytes() == (direct / "runs.pkl").read_bytes()
    assert os.environ.get("ENGINE_SMOKE_BARS") == "60"


def test_bundle_outside_repo_imports_and_smoke(tmp_path):
    """Kaggle-fidelity check: the built BUNDLE must work with cwd outside the repo.

    Extracts kaggle_entry.py's BUNDLE to tmp_path (outside the repo), loads
    every closure module there via spec_from_file_location with a clean
    sys.path (no repo root) and fails on any ImportError/ModuleNotFoundError
    (regression: v214/v215's `sys.path.insert + import trader_rl` failed on
    Kaggle while the in-repo smoke test passed); then runs the 60-bar
    ENGINE_SMOKE from the extracted dir (KAGGLE_INPUT_BASE ->
    artifacts/kaggle_stage; skipped if engine_data is absent).
    """
    import build_bundle as B
    files = B.closure(ROOT)
    src = (KERN / "kaggle_entry.py").read_text()
    b64 = src.split('BUNDLE = "', 1)[1].split('"', 1)[0]
    ext = tmp_path / "ext"
    ext.mkdir()
    zipfile.ZipFile(io.BytesIO(base64.b64decode(b64))).extractall(ext)
    assert ext.resolve() != ROOT.resolve()
    for rel in files:
        assert (ext / rel).exists(), f"bundle miss: {rel}"
    (ext / "_closure.json").write_text(json.dumps([f for f in files if f.endswith(".py")]))
    script = (
        "import importlib.util, json, pathlib\n"
        "lst = json.loads(pathlib.Path('_closure.json').read_text())\n"
        "bad = []\n"
        "for i, rel in enumerate(lst):\n"
        "    try:\n"
        "        spec = importlib.util.spec_from_file_location(f'bx{i}', str(pathlib.Path(rel)))\n"
        "        m = importlib.util.module_from_spec(spec)\n"
        "        spec.loader.exec_module(m)\n"
        "    except (ImportError, ModuleNotFoundError) as e:\n"
        "        bad.append(f'{rel}: {e}')\n"
        "    except Exception as e:\n"
        "        print(f'warn {rel}: {type(e).__name__}: {e}')\n"
        "if bad:\n"
        "    print('BUNDLE IMPORT FAIL')\n"
        "    [print(' ' + b) for b in bad]\n"
        "    raise SystemExit(1)\n"
        "print(f'bundle imports ok: {len(lst)} modules')\n"
    )
    clean = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "REPO_ROOT")}
    r = subprocess.run([sys.executable, "-c", script], cwd=ext, env=clean,
                       capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0, (r.stdout + r.stderr)[-4000:]
    assert "bundle imports ok" in r.stdout
    if not (ROOT / "artifacts/kaggle_stage/engine_data").exists():
        pytest.skip("engine_data absent")
    job = {"name": "smoke", "rows": [{"name": "BASE",
                                      "book_hook": "bear",
                                      "sleeve": {"rule": "inv", "k": 1.0, "kd": 1.7, "bear": True, "G": 2.0}}]}
    (ext / "job_smoke.json").write_text(json.dumps(job))
    env = dict(clean, REPO_ROOT=str(ext), KAGGLE_INPUT_BASE=str(ROOT / "artifacts/kaggle_stage"),
               KAGGLE_WORKING_BASE=str(ext / "kwork2"), ENGINE_SHIFTS="0",
               ENGINE_SMOKE_START="2024-03-01", ENGINE_SMOKE_BARS="60", ENGINE_NO_SCORE="1")
    s = subprocess.run([sys.executable, "kernel_run.py", "--job", "job_smoke.json"],
                       cwd=ext, env=env, capture_output=True, text=True, timeout=1800)
    assert s.returncode == 0, (s.stdout + s.stderr)[-4000:]
    res = json.loads((ext / "kwork2" / "out_eng" / "results.json").read_text())
    assert res["rows"]["BASE"]["bars"] == {"0": 60}
