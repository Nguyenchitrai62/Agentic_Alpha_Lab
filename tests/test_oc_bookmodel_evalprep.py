"""Tests for oc_bookmodel_evalprep (sealed candidate evaluation, no selection here)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVALPREP = ROOT / "research/tournament/oc_bookmodel_impl"  # noqa: F841 (kept for symmetry)
EVAL = ROOT / "research/tournament/oc_bookmodel_evalprep/eval_candidate.py"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
O1_FILES = ["member_A_O1_orders.parquet", "member_Aq_O1_orders.parquet",
            "member_B_tv.parquet", "member_Bq_tv.parquet"]
# v421 R2B1D17BFG2 reset-metric years (research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json)
EXP_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_FINAL = (4.648, 12.9)


def _load_eval():
    spec = importlib.util.spec_from_file_location("eval_candidate_t", EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_member_format_is_deployed():
    ref = pd.read_parquet(CACHE / "member_A_O1_orders.parquet")
    assert list(ref.columns) == SYMS
    assert ref.index.name == "t"
    assert str(ref.index.tz) == "UTC"


def test_candidate_blend_matches_deployed_d2(tmp_path):
    ev = _load_eval()
    for f in O1_FILES:
        shutil.copy(CACHE / f, tmp_path / f)
    cand = ev.candidate_books_d2(tmp_path)
    fw = ev._load("fw_t", ev.ROOT / "scripts/forward_v205.py")
    eu = ev._load("eu_t", ev.RD / "engine_user/engine_user.py")
    ref = fw.research_books_d2(eu)
    a = cand.reindex(ref.index).fillna(0.0)[SYMS]
    b = ref[SYMS]
    assert float((a - b).abs().max().max()) == 0.0


def test_candidate_d_files_are_ignored(tmp_path):
    """A D-named file in the candidate folder must not change the book (D is deployed)."""
    ev = _load_eval()
    for f in O1_FILES:
        shutil.copy(CACHE / f, tmp_path / f)
    before = ev.candidate_books_d2(tmp_path)
    fake_d = pd.DataFrame(999.0,
                          index=before.index[:10],
                          columns=SYMS)
    fake_d.index.name = "t"
    fake_d.to_parquet(tmp_path / "member_D_tv.parquet")
    after = ev.candidate_books_d2(tmp_path)
    assert float((before - after).abs().max().max()) == 0.0


def test_bucketing_accepts_c1_per_year_names(tmp_path):
    ev = _load_eval()
    idx = pd.date_range("2021-09-24", periods=8, freq="4h", tz="UTC")
    idx.name = "t"
    for name in ("member_C1_A_2021.parquet", "member_C1_B_2021.parquet",
                 "member_C1_Aq_2021.parquet", "member_C1_Bq_2021.parquet"):
        pd.DataFrame(0.01, index=idx, columns=SYMS).to_parquet(tmp_path / name)
    buckets = ev.bucket_member_files(tmp_path)
    assert all(len(buckets[k]) == 1 for k in ("A", "B", "Aq", "Bq"))
    m = ev.load_candidate_o1(tmp_path)
    assert set(m) == {"A", "B", "Aq", "Bq"}


def test_end_to_end_reproduces_v421_g2_dev_years(tmp_path):
    """Full harness with the CURRENT deployed O1 members reproduces v421 R2B1D17BFG2.

    Slow (4 phase sims, ~minutes) by design: this is the deployment-harness
    fidelity check. Prints dev years 2021-2024 only; 2025 stays sealed.
    """
    members = tmp_path / "members"
    members.mkdir()
    for f in O1_FILES:
        shutil.copy(CACHE / f, members / f)
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, str(EVAL), "--members", str(members),
                        "--out", str(out)], capture_output=True, text=True, timeout=1500)
    assert r.returncode == 0, r.stderr[-3000:]
    start = r.stdout.index("{")
    # the sealed-path line is not JSON; decode only the first JSON object
    dec = json.JSONDecoder()
    payload, _ = dec.raw_decode(r.stdout[start:])
    dev = [(y["R"], y["DD"]) for y in payload["dev_years"]]
    assert [y["anchor"] for y in payload["dev_years"]] == \
        ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
    assert dev == EXP_DEV
    assert "4.648" not in r.stdout  # sealed year must not leak without --final
    sealed = json.loads((out / "final_year.json").read_text())
    assert (sealed["final_year"]["R"], sealed["final_year"]["DD"]) == EXP_FINAL
    assert sealed["final_year"]["anchor"] == "2025-09-24"
    r2 = subprocess.run([sys.executable, str(EVAL), "--members", str(members),
                         "--out", str(out), "--final"],
                        capture_output=True, text=True, timeout=1500)
    assert r2.returncode == 0, r2.stderr[-3000:]
    assert "4.648" in r2.stdout  # --final unseals the display only
