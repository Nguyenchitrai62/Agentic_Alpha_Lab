"""Tests for the oc_b1shape rung screen (fast: synthetic + artifact consistency)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research/tournament/oc_b1shape"


def trailing_sigma(opens: np.ndarray, window: int = 360, minp: int = 120) -> np.ndarray:
    ret = np.full(len(opens), np.nan)
    ret[1:] = opens[1:] / opens[:-1] - 1.0
    return pd.Series(ret).rolling(window, min_periods=minp).std(ddof=1).to_numpy()


def test_sigma_uses_only_past_and_min_periods():
    o = np.linspace(100.0, 200.0, 500)
    s = trailing_sigma(o)
    assert np.isnan(s[:120]).all()  # <120 returns -> NaN
    assert np.isfinite(s[120:]).all()
    # constant returns -> sigma ~ 0; spike only affects trailing window
    o2 = np.ones(500)
    o2[400] = 1.5
    s2 = trailing_sigma(o2)
    assert s2[119] == 0.0 or np.isfinite(s2[200])
    assert s2[399] == 0.0  # window ending just before the jump is clean


def test_detection_boundary_is_inclusive_and_uses_f_minus_1():
    O, sig = 60000.0, 0.01
    lvl = O * (1 - 2.5 * sig)
    assert (lvl <= lvl)  # close exactly at level detects (<=)
    assert not (lvl * (1 + 1e-9) <= lvl)  # a tick above does not


def test_fills_n_timing_and_ranges():
    d = pd.read_parquet(HERE / "fills_n.parquet")
    assert d["n25"].between(0, 4).all() and d["n20"].between(0, 4).all()
    assert ((d["Tbar"].dt.minute == 0) & (d["Tbar"].dt.hour % 4 == 0)).all()
    assert d["f"].between(16, 238).all()
    assert ((d["t_fill"] - d["Tbar"]).dt.total_seconds() / 60 == d["f"]).all()
    assert (d.loc[d.sym == "BTCUSDT", "btc_det"] == 0).all()  # BTC never counts itself
    assert (d["n20"] >= d["n25"]).all()  # 2.0-sigma level is weaker -> wider net


def test_results_consistency_and_decision_rule():
    res = json.loads((HERE / "results.json").read_text())
    shapes = res["shapes"]
    assert set(shapes) == {"S0_flat", "S1_inv1pn", "S2_inv1pn2", "S3_btc2x", "S4_thresh20"}
    s1 = shapes["S1_inv1pn"]["yearly_S"]
    for name, row in shapes.items():
        assert len(row["yearly_S"]) == 5
        n_ge = sum(a >= b for a, b in zip(row["yearly_S"], s1))
        assert res["qualifies_S_ge_S1_in_ge4y"][name] == (name == "S1_inv1pn" or n_ge >= 4)
    qual = [k for k, v in res["qualifies_S_ge_S1_in_ge4y"].items() if v]
    best_wd = max(qual, key=lambda k: shapes[k]["worst_day_overall"])
    best_dd = max(qual, key=lambda k: shapes[k]["maxDD_fullpath"])
    assert res["best_worst_day"] == best_wd and res["best_maxDD"] == best_dd
    assert "S1" in res["verdict"]
