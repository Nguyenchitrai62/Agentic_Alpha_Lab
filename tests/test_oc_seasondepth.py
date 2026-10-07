"""oc_seasondepth tests: seasonal factor + D0-from-fill exits on synthetic tape."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_seasondepth"
sys.path.insert(0, str(OC))
import seasondepth as S

MK, TK = 0.0002, 0.00055


def _tape(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_weekly_slots_edges():
    idx = pd.DatetimeIndex([pd.Timestamp("2021-01-04 00:00", tz="UTC"),   # Monday
                            pd.Timestamp("2021-01-04 04:00", tz="UTC"),
                            pd.Timestamp("2021-01-10 23:59", tz="UTC")])  # Sunday
    q = S.weekly_slots(idx)
    assert list(q) == [0, 1, 41]


def test_factor_loud_vs_quiet_and_fallback():
    # 8 days of minutes: slot 0 loud (|ret| big), others flat.
    idx = pd.date_range("2021-01-04", periods=8 * 1440, freq="1min", tz="UTC")
    C = np.full(len(idx), 100.0)
    q = S.weekly_slots(idx)
    loud = np.where(q == 0)[0]
    C[loud] = 100.0 * np.exp(0.001 * ((np.arange(len(loud)) % 2) * 2 - 1))
    A = [pd.Timestamp("2021-01-12 00:00", tz="UTC")]
    tab = S.factor_table(C, idx, A, win_days=8)
    s = tab["2021-01-12"]
    assert len(s) == 42
    assert s[0] > 1.0  # loud slot above average
    assert s[1] < 1.0  # quiet slot below average (only boundary minutes move)
    # empty window -> all ones
    tab2 = S.factor_table(np.full(100, np.nan),
                          pd.date_range("2021-01-01", periods=100, freq="1min", tz="UTC"),
                          [pd.Timestamp("2021-01-12", tz="UTC")], win_days=8)
    assert bool((tab2["2021-01-12"] == 1.0).all())


def test_sigma_eff_shrinkage():
    assert abs(S.sigma_eff(0.01, 1.44) - 0.012) < 1e-12
    assert S.sigma_eff(0.01, np.nan) == 0.01
    assert S.sigma_eff(0.01, -2.0) == 0.01


def test_rule_deeper_in_loud_slot():
    sg, s, o1, k = 0.01, 1.44, 100.0, 3.0
    lv = o1 * (1 - k * sg)
    lvr = o1 * (1 - k * S.sigma_eff(sg, s))
    assert lvr < lv  # loud slot -> effectively deeper bid


def test_outcome_tp_shape():
    O, H, L, C = _tape()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = S.outcome_from_fill(H, L, C, O, f, lv, sg, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_find_fill_strict():
    low = np.array([100.0, 99.0, 98.0])
    assert S.find_fill(low, 99.0) == 2  # equal does NOT fill
    assert S.find_fill(np.array([np.nan, np.nan]), 50.0) is None


def test_stop_first_same_minute():
    O, H, L, C = _tape()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    sl = lv * (1 - 4 * sg)
    H[30] = tp + 1.0
    L[30] = sl - 1.0  # backstop not hit; close5 needs clock minute
    C[29] = sl - 0.01  # offset 29: (29+1)%5==0 -> stop signal at m=29
    O[30] = sl - 0.05
    ret, x, how = S.outcome_from_fill(H, L, C, O, f, lv, sg, 99.0, False)
    assert how == "stop"  # TP strictly-earlier rule: tie -> stop wins


def test_n_vector_threshold_and_nan():
    cmat = np.array([[90.0, np.nan, 97.0, 100.0]])
    oo = np.array([100.0])
    ss = np.array([0.01])  # thr = 100*(1-0.025) = 97.5
    n = S.n_vector(cmat, oo, ss)
    assert list(n) == [1, 0, 1, 0]  # exact<=counts; NaN never counts


def test_sigma_formula_excludes_current_bar():
    ob = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    sg = ob.pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isnan(sg[0]) and np.isnan(sg[1])
    # sg[3] uses returns ending at bar 2 only (bars 1,2), not bar 3
    r1, r2 = 101 / 100 - 1, 102 / 101 - 1
    assert abs(sg[3] - np.std([r1, r2], ddof=1)) < 1e-12


def test_daily_path_dd():
    recs = [("2021-01-01", 1.0), ("2021-01-02", -2.5), ("2021-01-03", 0.5)]
    Sm, Wd, DD, nd = S.daily_path(recs)
    assert abs(Sm - (-1.0)) < 1e-12 and abs(Wd - (-2.5)) < 1e-12
    assert abs(DD - 2.5) < 1e-12 and nd == 3
    assert S.daily_path([]) == (0.0, 0.0, 0.0, 0)
