"""oc_breadthdip tests: breadth gate + verbatim B1/D0 core on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_breadthdip"
sys.path.insert(0, str(OC))
import breadthdip as B

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_breadth_all_up_strict():
    d = np.array([101.0, 102.0, 103.0, 104.0, 105.0])
    s = np.full(5, 100.0)
    br, on = B.breadth_on_from_daily(d, s)
    assert br == 1.0 and on is True


def test_breadth_equal_is_not_up():
    d = np.array([101.0, 102.0, 100.0, 104.0, 105.0])
    s = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    br, on = B.breadth_on_from_daily(d, s)
    assert br == 0.8 and on is False


def test_breadth_nan_inputs_off():
    d = np.array([101.0, np.nan, 103.0, 104.0, 105.0])
    s = np.full(5, 100.0)
    br, on = B.breadth_on_from_daily(d, s)
    assert np.isnan(br) and on is False
    br2, on2 = B.breadth_on_from_daily(np.full(5, 101.0), np.full(5, np.nan))
    assert np.isnan(br2) and on2 is False


def test_breadth_requires_five():
    try:
        B.breadth_on_from_daily(np.full(4, 101.0), np.full(4, 100.0))
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-5 input")


def test_midnight_floor_and_exact():
    assert B.midnight_of_bar("2023-04-17 04:00+00:00") == pd.Timestamp("2023-04-17", tz="UTC")
    # exact midnight: M(T) = T (daily close ending at T is known at T)
    assert B.midnight_of_bar("2023-04-17 00:00+00:00") == pd.Timestamp("2023-04-17", tz="UTC")
    assert B.midnight_of_bar("2023-04-17 20:00+00:00") == pd.Timestamp("2023-04-17", tz="UTC")


def test_rule_weight_fixed_08():
    assert B.RULE_SCALE == 0.8
    assert B.rule_weight(1.0, True) == 0.8
    assert B.rule_weight(0.5, True) == 0.4
    assert B.rule_weight(0.5, False) == 0.5
    assert B.rule_weight(0.0, True) == 0.0


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert B.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]


def test_size_mult_and_fill_strict():
    assert B.size_mult(0) == 1.0
    assert abs(B.size_mult(4) - 0.2) < 1e-12
    lv = 100.0
    assert B.find_fill(np.array([100.0, 100.0]), np.array([lv, lv])) is None
    assert B.find_fill(np.array([100.0, 99.99]), np.array([lv, lv])) == 1


def test_exit_tp_and_stop_first():
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    tp = px * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = B.outcome_from_fill(H, L, C, O, f, px, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / px - 1 - 2 * MK)) < 1e-12
    O2, H2, L2, C2 = _flat(o=px)
    H2[29] = px * (1 + sg) + 0.01
    C2[29] = px * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how2 = B.outcome_from_fill(H2, L2, C2, O2, f, px, sg, 99.0, False)
    assert how2 == "stop"


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    assert B.n_vector(closes, np.full(4, o), np.full(4, sg)).tolist() == [0, 1, 0]


def test_sma200_uses_strictly_prior_days():
    # SMA200(M) = mean of D over M-200d..M-1d: replicate run logic on synthetic
    mids = pd.date_range("2021-01-01", periods=210, freq="1D", tz="UTC")
    daily = pd.DataFrame({"c": np.arange(210, dtype=float)}, index=mids)
    sma = daily.shift(1).rolling(200, min_periods=200).mean()
    assert np.isnan(sma["c"].iloc[199])  # only 199 priors -> NaN
    assert abs(sma["c"].iloc[200] - 99.5) < 1e-9  # mean(daily 0..199), excludes own close
    assert sma["c"].iloc[201] == pytest_approx_mean(1, 200)
    # spot: SMA at last midnight excludes that midnight's own close
    assert sma["c"].iloc[-1] == daily["c"].iloc[-201:-1].mean()


def pytest_approx_mean(a, b):
    return (a + b) / 2.0


def test_plan_prefrozen_and_hourly_has_majors():
    plan = (OC / "PLAN.md").read_text()
    assert "breadth_on(T) iff breadth(T) == 1.0 exactly" in plan
    assert "w_rule = w_base * 0.8 iff breadth_on(T)" in plan
    assert "NO renormalisation" in plan
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["sym"])
    syms = set(h["sym"].unique().tolist())
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"} <= syms
