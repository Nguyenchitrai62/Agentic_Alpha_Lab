"""Tests for oc_bookdipnet (idea #19). No outcome tuning; causality + math checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_bookdipnet"))
import compute_bookdipnet as cd

D = ROOT / "research" / "tournament" / "oc_bookdipnet"


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "PLAN.md").exists()
    assert (D / "compute_bookdipnet.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_replica_counts_and_bit_for_bit_path():
    r = _res()
    assert r["n_bars"] == 10944
    assert r["n_rungs"] == 5466
    assert r["checks"]["n_attrib"] == 10944
    assert r["checks"]["n_rungs"] == 5466
    assert abs(r["checks"]["attrib_vs_raw_eq_rel_diff"]) < 1e-9


def test_strict_zero_vs_inclusive_census():
    r = _res()
    assert r["guard_coin_bars"] == 0
    assert r["overlap_coin_bars"] == 0
    assert r["guard_coin_bars_inc"] == 43 + 73 + 86 + 97 + 64 == 363
    per = r["per_year"]
    assert [y["guard_coin_bars"] for y in per] == [0, 0, 0, 0, 0]
    assert [y["guard_coin_bars_inc"] for y in per] == [43, 73, 86, 97, 64]
    assert r["decision"]["PROMISING"] is False
    assert r["decision"]["maxdd_years_improved"] == 0
    assert r["decision_inc"]["PROMISING"] is False
    assert r["decision_inc"]["maxdd_years_improved"] == 3
    assert r["decision_inc"]["sum_years_not_lower"] == 3


def test_guard_mask_longs_only_and_boundary_convention():
    thr = {s: 1.0 for s in cd.SYMS}
    openW = np.full((2, 5), 2.0)  # overlap everywhere
    tgt = np.array([[0.1, -0.1, 0.0, 0.2, -0.3], [0.1, -0.1, 0.0, 0.2, -0.3]])
    gm = cd.guard_mask(openW, tgt, thr)
    assert gm[0].tolist() == [True, False, False, True, False]
    # synthetic boundary: one rung filled prev bar, exit exactly at B
    B = pd.DatetimeIndex([pd.Timestamp("2022-01-01 04:00", tz="UTC"),
                          pd.Timestamp("2022-01-01 08:00", tz="UTC")])
    ru = pd.DataFrame(dict(
        fill_t=pd.to_datetime(["2022-01-01 05:00"], utc=True),
        exit_t=pd.to_datetime(["2022-01-01 08:00"], utc=True),
        symbol=["BTCUSDT"], weight=[10.0]))
    o_strict, _, _ = cd.overlap_open_weights(B, ru, inclusive=False)
    o_inc, _, _ = cd.overlap_open_weights(B, ru, inclusive=True)
    a = cd.SYMS.index("BTCUSDT")
    assert o_strict[1, a] == 0.0  # exit == B excluded by strict
    assert o_inc[1, a] == 10.0  # kept by inclusive
    assert o_inc[0, a] == 0.0  # fill not in [B-4h, B) for the first bar


def test_overlap_causal_on_real_rungs():
    B, _, _, _, _ = cd.load_attrib()
    rungs = cd.load_rungs()
    openW_full, _, thr = cd.overlap_open_weights(B, rungs, inclusive=True)
    P = B[len(B) // 2]
    future = rungs[rungs["fill_t"] >= P]
    assert len(future) > 0
    past = rungs[rungs["fill_t"] < P]
    openW_past, _, _ = cd.overlap_open_weights(B, past, inclusive=True)
    same = B <= P
    np.testing.assert_allclose(openW_full[same], openW_past[same], rtol=1e-12, atol=1e-12)


def test_year_partition_covers_attrib_once():
    B, _, _, _, _ = cd.load_attrib()
    masks = cd.year_masks(B)
    assert len(masks) == 5
    total = np.zeros(len(B), dtype=int)
    for _, m in masks:
        total += m.astype(int)
    assert bool((total == 1).all())
    assert int(total.sum()) == 10944
