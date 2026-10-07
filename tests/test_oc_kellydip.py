"""Tests for oc_kellydip (fast: synthetic solver/DD/n checks + artifact consistency)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_kellydip"
sys.path.insert(0, str(OC))
import compute_kelly as K

RES = json.loads((OC / "results.json").read_text())


def test_kelly_closed_form_coin_flip():
    # 6 x +1, 4 x -1 -> f* = 2p-1 = 0.2
    z = np.array([1.0] * 6 + [-1.0] * 4)
    fs, capped = K.kelly_star(z)
    assert not capped and abs(fs - 0.2) < 1e-9


def test_kelly_negative_ev_is_zero():
    z = np.array([1.0] * 3 + [-1.0] * 7)
    fs, _ = K.kelly_star(z)
    assert fs == 0.0


def test_kelly_all_win_hits_cap():
    z = np.array([0.01, 0.02, 0.005])
    fs, capped = K.kelly_star(z)
    assert capped and fs == 20.0


def test_kelly_beats_grid_neighbours():
    rng = np.random.default_rng(0)
    z = np.concatenate([rng.normal(0.004, 0.03, 800), [-0.25, -0.3]])
    fs, capped = K.kelly_star(z)
    assert not capped and fs > 0
    g0 = K.growth(z, fs)
    for df in (-0.05, -0.01, 0.01, 0.05):
        assert g0 >= K.growth(z, max(fs + df, 0.0)) - 1e-12
    assert K.growth(z, fs) == max(K.growth(z, fs), K.growth(z, 1.0))


def test_dd_stats_and_linearity():
    ds = pd.Series([0.5, -0.3, -0.4, 0.1, -0.5, 0.8])
    mdd = K.dd_stats(ds)
    c = ds.to_numpy().cumsum()
    assert abs(mdd - float(np.min(c - np.maximum.accumulate(c)))) < 1e-12
    assert abs(K.dd_stats(ds * 1.7) - 1.7 * mdd) < 1e-12


def test_count_n_toy_windows():
    T0 = pd.Timestamp("2023-01-02 04:00", tz="UTC")
    tfill = np.array([T0 + pd.Timedelta(minutes=m) for m in (20, 25, 60, 200)])
    sym = np.array(["BTCUSDT", "ETHUSDT", "BTCUSDT", "SOLUSDT"])
    T = np.array([T0] * 4)
    n = K.count_n(tfill, sym, T)
    # row0 BTC@20: ETH@25 within 15m -> {ETH} = 1 (own second rung excluded)
    # row1 ETH@25: BTC within 15m -> {BTC} = 1
    # row2 BTC@60: nobody within 15m -> 0 ; row3 SOL@200 -> 0
    assert list(n) == [1, 1, 0, 0]


def test_count_n_excludes_self_coin_and_far_bars():
    T0 = pd.Timestamp("2023-01-02 04:00", tz="UTC")
    T1 = pd.Timestamp("2023-01-02 08:00", tz="UTC")
    tfill = np.array([T0 + pd.Timedelta(minutes=20), T0 + pd.Timedelta(minutes=22), T1 + pd.Timedelta(minutes=20)])
    sym = np.array(["BTCUSDT", "BTCUSDT", "ETHUSDT"])
    T = np.array([T0, T0, T1])
    n = K.count_n(tfill, sym, T)
    assert list(n) == [0, 0, 0]  # same-coin rungs and other bars do not count


def test_results_internal_consistency():
    u = RES["universe"]
    assert u["majors_R2_5y"] == 5498 and sum(u["per_year"]) == 5498
    assert u["f_dep"] == 1.7 and u["outcome"] == "y1.0"
    assert [y["year"] for y in RES["years"]] == u["anchors"]
    for y in RES["years"]:
        for w in ("flat", "shrunk"):
            r = y[w]
            assert r["f_star"] >= 0 and r["maxDD_1"] <= 0 and r["DD_dep"] <= 0
            assert abs(r["DD_dep"] - 1.7 * r["maxDD_1"]) < 1e-6
            if r["f_star"] > 0:
                assert abs(r["dep_over_fstar"] - 1.7 / r["f_star"]) < 0.02
            assert abs(r["dep_over_fDD20"] - 1.7 / r["f_DD20"]) < 0.02
            assert abs(r["dep_over_fDD15"] - 1.7 / r["f_DD15"]) < 0.02
            if r["G_dep"] is not None:
                assert r["G_dep"] <= r["G_star"] + 1e-9
            assert r["min_1_plus_dep_z"] > 0  # deployed feasible every year
    sh = RES["n_hist_share"]
    for k in u["anchors"] + ["overall"]:
        assert abs(sum(sh[k][s] for s in "01234") - 1.0) < 2e-3


def test_results_match_report_and_b1shape_anchor():
    rep = (OC / "REPORT.md").read_text()
    assert "Deployed x1.7" in rep and "2022" in rep
    b1 = json.loads((ROOT / "research/tournament/oc_b1shape/results.json").read_text())
    s0 = b1["shapes"]["S0_flat"]
    y22 = [y for y in RES["years"] if y["year"] == "2022-09-24"][0]
    assert abs(y22["flat"]["worst_day_1"] - s0["worst_day_per_year"][1]) < 1e-3
    assert abs(y22["flat"]["worst_day_1"] - (-1.9236)) < 1e-3  # S0 2022 worst day
    assert abs(y22["flat"]["maxDD_1"] - (-2.2818)) < 1e-3  # S0 full-path maxDD, driven by 2022
    # headline descriptive facts
    assert y22["flat"]["dep_over_fstar"] > 1 > [y for y in RES["years"] if y["year"] == "2021-09-24"][0]["flat"]["dep_over_fstar"]
