"""Tests for oc_bookexit (idea #31). No outcome tuning; causality + math checks."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_bookexit"))
import compute_bookexit as bx

bx.VOL_N = 3
bx.VOL_MIN = 2
bx.TREND_N = 2


def _grid(n, start="2022-01-01"):
    t0 = pd.Timestamp(start, tz="UTC")
    return pd.DatetimeIndex([t0 + pd.Timedelta(hours=4 * i) for i in range(n)])


def _frames(grid, wmap, rmap, high=101.0, low=99.0, opens_v=100.0, atr_v=1.0):
    w = pd.DataFrame({s: np.zeros(len(grid)) for s in bx.SYMS}, index=grid)
    r = pd.DataFrame({s: np.zeros(len(grid)) for s in bx.SYMS}, index=grid)
    o = pd.DataFrame({s: np.full(len(grid), opens_v) for s in bx.SYMS}, index=grid)
    for s, v in wmap.items():
        w[s] = np.asarray(v, dtype=float)
    for s, v in rmap.items():
        r[s] = np.asarray(v, dtype=float)
    hlc, atr = {}, {}
    for s in bx.SYMS:
        hlc[s] = pd.DataFrame({"high": np.full(len(grid), high),
                               "low": np.full(len(grid), low),
                               "close": np.full(len(grid), opens_v)}, index=grid)
        atr[s] = pd.Series(np.full(len(grid), atr_v), index=grid)
    return w, r, hlc, atr, o


def test_segmentation_and_cost_partition():
    grid = _grid(10)
    w, r, hlc, atr, o = _frames(
        grid, {"BTCUSDT": [0.0, 0.0, 0.0, 0.0, 0.1, 0.15, 0.0, -0.1, 0.0, 0.0]},
        {"BTCUSDT": [0.0, 0.0, 0.005, -0.004, 0.01, -0.5, 0.0, -0.2, 0.0, 0.0]})
    ep, _ = bx.build_episodes(w, r, hlc, atr, o)
    btc = ep[ep["coin"] == "BTCUSDT"].sort_values("a").reset_index(drop=True)
    assert len(btc) == 2
    assert (btc.loc[0, "a"], btc.loc[0, "b"]) == (4, 5)
    assert (btc.loc[1, "a"], btc.loc[1, "b"]) == (7, 7)
    assert btc.loc[0, "gross"] == round(0.1 * 0.01 + 0.15 * -0.5, 8)
    assert btc.loc[0, "net"] == round(btc.loc[0, "gross"] - 0.0005 * 0.3, 8)
    assert btc.loc[1, "gross"] == round(-0.1 * -0.2, 8)
    assert btc.loc[1, "net"] == round(0.02 - 0.0005 * 0.2, 8)
    assert btc.loc[0, "close_t"] == grid[6]
    assert btc.loc[1, "close_t"] == grid[8]


def test_label_stop_first_same_bar():
    grid = _grid(6)
    # bar 3 touches +1.5A (high 102) AND -1.0A (low 98.5): adverse first -> 0
    w, r, hlc, atr, o = _frames(grid, {"BTCUSDT": [0.0, 0.0, 0.0, 0.1, 0.0, 0.0]}, {})
    hlc["BTCUSDT"] = pd.DataFrame({"high": [101.0, 101.0, 101.0, 102.0, 101.0, 101.0],
                                   "low": [99.0, 99.0, 99.0, 98.5, 99.0, 99.0],
                                   "close": [100.0] * 6}, index=grid)
    ep, _ = bx.build_episodes(w, r, hlc, atr, o)
    assert len(ep) == 1 and ep.loc[0, "label"] == 0
    # same setup but low never touches -1.0A -> label 1
    w2, r2, hlc2, atr2, o2 = _frames(grid, {"BTCUSDT": [0.0, 0.0, 0.0, 0.1, 0.0, 0.0]}, {})
    hlc2["BTCUSDT"] = pd.DataFrame({"high": [101.0, 101.0, 101.0, 102.0, 101.0, 101.0],
                                    "low": [99.5, 99.5, 99.5, 99.5, 99.5, 99.5],
                                    "close": [100.0] * 6}, index=grid)
    ep2, _ = bx.build_episodes(w2, r2, hlc2, atr2, o2)
    assert len(ep2) == 1 and ep2.loc[0, "label"] == 1
    assert bool(ep2.loc[0, "tp_hit"]) is True


def test_tp_rule_value_math():
    grid = _grid(6)
    w, r, hlc, atr, o = _frames(grid, {"BTCUSDT": [0.0, 0.0, 0.0, 0.1, 0.0, 0.0]}, {})
    hlc["BTCUSDT"] = pd.DataFrame({"high": [101.0, 101.0, 101.0, 102.0, 101.0, 101.0],
                                   "low": [99.5, 99.5, 99.5, 99.5, 99.5, 99.5],
                                   "close": [100.0] * 6}, index=grid)
    ep, _ = bx.build_episodes(w, r, hlc, atr, o)
    # 1.0*(A/E)*|w| - 2*FEE*|w| = 1.0*(1/100)*0.1 - 2*0.0005*0.1
    assert ep.loc[0, "rule_net_full"] == round(0.001 - 0.0001, 8)


def test_train_mask_embargo_edge():
    A = bx.ANCHORS[0]
    assert not (A - bx.EMBARGO < A - bx.EMBARGO)  # equality is strictly excluded
    assert (A - bx.EMBARGO - pd.Timedelta(hours=4)) < (A - bx.EMBARGO)
    closes = pd.DatetimeIndex([A - bx.EMBARGO - pd.Timedelta(hours=4), A - bx.EMBARGO])
    mask = np.asarray(closes < A - bx.EMBARGO)
    assert mask.tolist() == [True, False]


def test_features_causal_under_future_perturbation():
    gridA = _grid(8)
    wA = {"BTCUSDT": [0.0, 0.0, 0.0, 0.0, 0.1, 0.15, 0.0, 0.0]}
    rA = {"BTCUSDT": [0.0, 0.001, 0.002, -0.001, 0.01, 0.02, 0.0, 0.0]}
    w, r, hlc, atr, o = _frames(gridA, wA, rA)
    epA, _ = bx.build_episodes(w, r, hlc, atr, o)
    assert len(epA) >= 1
    gridB = _grid(11)  # same start, 3 extra bars with wild future weights/returns
    wB = {"BTCUSDT": [0.0, 0.0, 0.0, 0.0, 0.1, 0.15, 0.0, 0.0, 0.9, -0.9, 0.9]}
    rB = {"BTCUSDT": [0.0, 0.001, 0.002, -0.001, 0.01, 0.02, 0.0, 0.0, 0.5, -0.5, 0.5]}
    w2, r2, hlc2, atr2, o2 = _frames(gridB, wB, rB)
    epB, _ = bx.build_episodes(w2, r2, hlc2, atr2, o2)
    m = epA.merge(epB, on=["coin", "a", "b"], suffixes=("", "_f"))
    assert len(m) >= 1
    for c in bx.FEATS + ["label", "gross", "net"]:
        assert np.allclose(m[c].to_numpy(float), m[c + "_f"].to_numpy(float)), c
