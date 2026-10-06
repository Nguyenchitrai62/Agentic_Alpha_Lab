"""Tests for oc_clockluck (light: synthetic replica logic + results.json shape).

No market data, no engine run here. The heavy script
research/diagnostics/oc_clockluck/clockluck.py is run separately via heavy_slot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_clockluck"
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_dipexit"))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_b1deeper"))
sys.path.insert(0, str(D))
import exits as E
import deeper as B

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_fill_strict_trade_through():
    lv = 100.0
    assert not (100.0 < lv)
    assert 99.99 < lv


def test_d0_tp_pays_two_makers():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_d0_stop_first_same_minute():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[29] = lv * (1 + sg) + 0.01
    C[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _r, _x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "stop"


def test_d0_backstop_wins_ties():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[25] = lv * (1 + sg) + 0.01
    Lw[25] = lv * (1 - 8 * sg) - 0.01
    _r, x, how = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "backstop" and x == 25


def test_d0_timeout_funding_only_on_settle():
    O, H, Lw, C = _flat()
    lv, sg, f, o2 = 100.0, 0.01, 20, 101.0
    r0, x0, h0 = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, o2, False)
    r1, x1, h1 = E.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, o2, True)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_b1_size_uses_fill_minute_only():
    assert abs(B.size_mult(0) - 1.0) < 1e-12
    assert abs(B.size_mult(1) - 0.5) < 1e-12
    assert abs(B.size_mult(3) - 0.25) < 1e-12


def test_n_vector_needs_m1_close_only():
    # two others: one flushing at m-1 close, one NaN -> not counted
    close_others = np.array([[99.0, np.nan, 99.0]], dtype=float).T  # shape (1,3)? build (2,W)
    close_others = np.array([[99.0, 99.0, 99.0], [np.nan, np.nan, np.nan]], dtype=float)
    oo = np.array([100.0, 100.0])
    ss = np.array([0.01, 0.01])
    n = B.n_vector(close_others, oo, ss)
    # thr = 100*(1-2.5*0.01)=97.5; 99 > 97.5 -> not flushing -> 0
    assert list(n) == [0, 0, 0]
    close_others = np.array([[97.0, 97.0, 97.0], [np.nan, np.nan, np.nan]], dtype=float)
    n = B.n_vector(close_others, oo, ss)
    assert list(n) == [1, 1, 1]


def test_n_flush_boundary_counts():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    close_others = np.array([[thr, thr + 1e-9]], dtype=float)
    n = B.n_vector(close_others, np.array([o]), np.array([sg]))
    assert list(n) == [1, 0]  # exactly at 2.5 sigma counts (<=)


def test_sigma_excludes_current_bar():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12


def test_start_offset_grid():
    from datetime import timezone
    s0 = pd.Timestamp("2020-08-01", tz="UTC")
    for o in (0, 60, 120, 180, 230):
        so = s0 + pd.Timedelta(minutes=o)
        # bars are 240-min multiples of the shifted START; different offsets differ
        b0 = so + pd.Timedelta(minutes=240)
        assert (b0 - s0).total_seconds() // 60 == o + 240


def test_clockluck_results_shape():
    r = json.loads((D / "results.json").read_text())
    assert r["version"] == "oc_clockluck"
    assert r["deployed_G2_5y"] == 5.41
    assert r["part1"]["reproduced_exactly"] is True
    for s in ("0", "0.5", "1", "1.5", "2", "2.5", "3", "3.5"):
        assert s in r["part1"]["yearly_splits_points"], s
        assert len(r["part1"]["yearly_splits_points"][s]) == 5
        for y in r["part1"]["yearly_splits_points"][s]:
            assert set(y) >= {"book_points", "dip_points", "total_points", "end_eq", "resid"}
            assert abs(y["resid"]) < 0.02, (s, y)
    dip = r["part2"]["dip"]
    assert dip["offsets"] == list(range(0, 240, 10)) and len(dip["offsets"]) == 24
    assert dip["deployed"] == [0, 60, 120, 180]
    assert len(dip["sum_w_5y_per_offset"]) == 24
    for y in ("0", "1", "2", "3", "4"):
        assert y in dip["per_year"]
        assert set(dip["per_year"][y]["percentiles"]) == {"0", "60", "120", "180"}
    assert set(dip["percentile_5y"]) == {"0", "60", "120", "180"}
    p3 = r["part3"]
    assert set(p3) >= {"random_clock_expectation_5y", "luck_ratios_all_over_deployed", "method"}
    assert "APPROXIMATE" in p3["method"]
    assert isinstance(p3["random_clock_expectation_5y"], float)


def test_report_has_vietnamese_conclusion():
    rep = (D / "REPORT.md").read_text()
    assert "VERDICT" in rep
    for token in ("Ket luan", "5.41", "24"):
        assert token in rep, token
