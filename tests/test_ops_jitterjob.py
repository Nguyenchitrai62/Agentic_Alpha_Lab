"""Tests for the G2 joint-jitter robustness job (ops_jitterjob).

Covers, without uploads, credentials, or any full 5-year run:
  1. jobs/jitter_g2.json parses: 13 rows (1 base + 12 joint-jitter), base row
     equals oc_expiry4p RUNS["R2B1D17BFG2"] and job_example.json base exactly
     (reproduction gate: full Kaggle run must hit v421 5.41 / 16.91 / 16.82).
  2. jitter draws are seeded (seed 20261006 in file), independent uniform
     +-10% on kd/G/k jointly, reproducible from numpy default_rng.
  3. sleeve keys are within the harness schema (rule/k/kd/G/bear/cool/bm/xrp);
     TP/stop multiples are absent because engine_harness exposes no such
     sleeve key (left out per assignment).
  4. all book_hooks are builtins (no custom hook module needed).
  5. local smoke (shift 0, 60 bars from 2024-03-01, base row only):
     kernel_run.main output is byte/compare-equal to the direct
     engine_harness.run_rows call (bundle-report smoke contract).

Run: .venv/Scripts/python.exe -m pytest tests/test_ops_jitterjob.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
KERN = ROOT / "artifacts/kaggle_stage/engine_kernel"
JOB = KERN / "jobs" / "jitter_g2.json"
sys.path.insert(0, str(KERN))

ALLOWED_SLEEVE_KEYS = {"rule", "k", "kd", "G", "bear", "cool", "bm", "xrp"}
BASE_SLEEVE = {"rule": "inv", "k": 1.0, "kd": 1.7, "bear": True, "G": 2.0}
BASE_BOUNDS = {"kd": (1.7 * 0.9, 1.7 * 1.1), "G": (2.0 * 0.9, 2.0 * 1.1), "k": (1.0 * 0.9, 1.0 * 1.1)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _job():
    return json.loads(JOB.read_text())


def test_job_parses_and_base_reproduces_v421_cfg():
    job = _job()
    assert job["perturb"]["seed"] == 20261006
    assert len(job["rows"]) == 13, "1 base + 12 jitter rows"
    base = job["rows"][0]
    assert base["name"] == "R2B1D17BFG2"
    assert base["book_hook"] == "bear"
    assert base["sleeve"] == BASE_SLEEVE
    oc = _load("oc4p_ref_j", ROOT / "research/diagnostics/oc_expiry4p/oc_expiry4p.py")
    assert base["sleeve"] == {k: v for k, v in oc.RUNS["R2B1D17BFG2"].items()}
    example = json.loads((KERN / "job_example.json").read_text())
    assert base["sleeve"] == example["rows"][0]["sleeve"]
    assert base["book_hook"] == example["rows"][0]["book_hook"]
    # Full-run reproduction gate (checked on Kaggle, not locally): the BASE row
    # must equal the v421 run.log row (5y 5.41 %/mo, max yearly DD 16.91,
    # full-path DD 16.82); else stop and report.


def test_jitter_rows_seeded_bounds_and_joint():
    job = _job()
    rng = np.random.default_rng(job["perturb"]["seed"])
    jitter = job["rows"][1:]
    assert [r["name"] for r in jitter] == [f"R2B1D17BFG2_J{i:02d}" for i in range(1, 13)]
    seen = set()
    for r in jitter:
        u_kd, u_G, u_k = rng.random(), rng.random(), rng.random()
        want = {"rule": "inv", "bear": True,
                "kd": round(1.7 * (0.9 + 0.2 * u_kd), 4),
                "G": round(2.0 * (0.9 + 0.2 * u_G), 4),
                "k": round(1.0 * (0.9 + 0.2 * u_k), 4)}
        assert r["sleeve"] == want, r["name"]
        assert r["book_hook"] == "bear"
        assert set(r["sleeve"]) <= ALLOWED_SLEEVE_KEYS
        for key, (lo, hi) in BASE_BOUNDS.items():
            assert lo - 1e-12 <= r["sleeve"][key] <= hi + 1e-12, (r["name"], key)
        seen.add((r["sleeve"]["kd"], r["sleeve"]["G"], r["sleeve"]["k"]))
    assert len(seen) == 12, "joint independent draws must give 12 distinct triples"
    assert any(r["sleeve"]["kd"] != 1.7 for r in jitter)
    assert any(r["sleeve"]["G"] != 2.0 for r in jitter)
    assert any(r["sleeve"]["k"] != 1.0 for r in jitter)


def test_no_tp_stop_keys_and_no_custom_hook_needed():
    job = _job()
    for r in job["rows"]:
        assert not any(k in r["sleeve"] for k in ("tp", "sl", "tp_mult", "sl_mult", "TP_MULT")), r["name"]
    import hooks as HK
    for r in job["rows"]:
        assert r["book_hook"] in HK.BUILTINS, r["name"]
    # engine_harness exposes no TP/stop-multiplier sleeve key: kd/k/G are read
    # via cfg.get, m_sleeve_sl appears only as a read default for the xrp
    # coin-specific override; there is no tp_mult/sl key (left out per brief).


def test_smoke_kernel_matches_direct_base(tmp_path, monkeypatch):
    import engine_harness as H
    import kernel_run as KR
    job = _job()
    base_row = job["rows"][0]
    mini = {"name": "jitter_smoke", "rows": [base_row]}
    env = {"REPO_ROOT": str(ROOT), "KAGGLE_INPUT_BASE": str(ROOT),
           "ENGINE_SHIFTS": "0", "ENGINE_SMOKE_START": "2024-03-01",
           "ENGINE_SMOKE_BARS": "60", "ENGINE_NO_SCORE": "1"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    jp = tmp_path / "job.json"
    jp.write_text(json.dumps(mini))
    direct = tmp_path / "direct"
    res = H.run_rows(mini, direct, ROOT)
    assert (direct / "results.json").exists() and (direct / "runs.pkl").exists()
    assert res["rows"]["R2B1D17BFG2"]["bars"] == {0: 60}
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
