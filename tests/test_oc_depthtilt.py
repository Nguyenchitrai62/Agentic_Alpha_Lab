"""oc_depthtilt tests: tilt vector, D0 exit, B1 size, G-cap walk, control, scoring (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_depthtilt"
sys.path.insert(0, str(OC))
import depthtilt as D


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_tilt_vector_frozen_and_neutral():
    # raw k/2.5 renormalised per coin-bar to sum 5.0 (ex-ante exposure neutral)
    assert set(D.TILT) == {2.5, 3.0, 3.5, 4.0, 5.0}
    assert abs(sum(D.TILT.values()) - 5.0) < 1e-12
    assert abs(D.tilt_mult(2.5) - 5.0 / 7.2) < 1e-12
    assert abs(D.tilt_mult(3.0) - 6.0 / 7.2) < 1e-12
    assert abs(D.tilt_mult(3.5) - 7.0 / 7.2) < 1e-12
    assert abs(D.tilt_mult(4.0) - 8.0 / 7.2) < 1e-12
    assert abs(D.tilt_mult(5.0) - 10.0 / 7.2) < 1e-12
    # monotone: deeper rungs carry more nominal size
    ts = [D.tilt_mult(k) for k in (2.5, 3.0, 3.5, 4.0, 5.0)]
    assert ts == sorted(ts) and ts[0] < 1.0 < ts[-1]


def test_rule_weight_is_b1_times_tilt():
    for k in (2.5, 3.0, 3.5, 4.0, 5.0):
        for n in (0, 1, 4):
            assert abs(D.rule_weight(n, k) - D.tilt_mult(k) * D.size_mult(n)) < 1e-12
    assert abs(D.rule_weight(0, 2.5) - 0.69444444) < 1e-6
    assert abs(D.rule_weight(1, 5.0) - 1.38888889 / 2) < 1e-6


def test_fill_strict_trade_through():
    low = np.full(223, 100.0)
    low[5] = 100.0  # equal level never fills
    assert D.find_fill(low, 100.0) is None
    low[5] = 99.999
    assert D.find_fill(low, 100.0) == 5
    assert D.find_fill(np.full(223, np.nan), 100.0) is None


def test_n_exact_boundary_and_nan():
    cmat = np.array([[97.5, 97.51, np.nan]])
    oo = np.array([100.0])
    ss = np.array([0.01])
    n = D.n_vector(cmat, oo, ss)
    assert n.tolist() == [1, 0, 0]  # exact 97.5 counts; NaN never counts
    assert D.size_mult(0) == 1.0
    assert abs(D.size_mult(3) - 0.25) < 1e-12


def test_n_causal_only_closed_minute():
    # n at live minute m uses the close at T+m-1 only: a flush print at C[m]
    # must not leak into n[m] (input window ends at ...+LIVE_B, i.e. m-1).
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)  # 97.5
    c_early = np.full(4, 100.0)
    c_late = np.full(4, 100.0)
    c_late[2] = thr - 0.01  # flush at window position 2 only
    n = D.n_vector(np.array([c_late]), np.array([o]), np.array([sg]))
    assert n.tolist() == [0, 0, 1, 0]
    assert n.shape == c_early.shape


def test_sigma_excludes_the_bar():
    import pandas as pd

    ob = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    sg = ob.pct_change().rolling(360, min_periods=2).std(ddof=1).shift(1).to_numpy()
    # shift(1): sigma at bar j never sees O_j (last value uses returns up to j-1)
    assert np.isnan(sg[0]) and np.isnan(sg[1]) and np.isnan(sg[2])
    assert np.isfinite(sg[3])
    assert abs(sg[3] - np.std([1 / 100, 1 / 101], ddof=1)) < 1e-12


def test_d0_tp_and_stop_first():
    O, H, L, C = _flat()
    lv, sg, o2 = 100.0, 0.01, 100.0
    H[60] = 101.01  # TP at 101 touched strictly
    ret, x, how = D.outcome_from_fill(H, L, C, O, 50, lv, sg, o2, False)
    assert how == "tp" and x == 60
    assert abs(ret - (101.0 / 100 - 1 - 2 * 0.0002)) < 1e-12
    O2, H2, L2, C2 = _flat()
    sl = lv * (1 - 4 * sg)  # 96
    H2[70] = 102.0
    C2[69] = sl - 0.01  # clock minute 69 ((69+1)%5==0) triggers close5 stop
    _, _, how2 = D.outcome_from_fill(H2, L2, C2, O2, 50, lv, sg, o2, False)
    assert how2 == "stop"


def test_d0_backstop_priority_and_funding():
    O, H, L, C = _flat()
    lv, sg = 100.0, 0.01
    L[60] = 90.0  # bl = 92 touched
    H[60] = 105.0  # TP also touched same minute -> backstop wins
    _, _, how = D.outcome_from_fill(H, L, C, O, 50, lv, sg, 100.0, False)
    assert how == "backstop"
    O3, H3, L3, C3 = _flat()
    r0, _, h0 = D.outcome_from_fill(H3, L3, C3, O3, 50, lv, sg, 100.0, False)
    r1, _, h1 = D.outcome_from_fill(H3, L3, C3, O3, 50, lv, sg, 100.0, True)
    assert h0 == "time" and h1 == "time"
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_cap_walk_tilted_weights_cut_skip():
    # deep (heavy) rung consumes more room under the tilt than base would
    f = np.array([10, 11, 12])
    x = np.array([200, 200, 200])
    w_rule = np.array([D.rule_weight(0, 2.5), D.rule_weight(0, 5.0), D.rule_weight(0, 2.5)])
    kept = D.gross_cap_weights(f, x, w_rule, [0, 1, 2], G=2.0)
    assert abs(kept[0] - 0.69444444) < 1e-6
    assert abs(kept[1] - (2.0 - 0.69444444)) < 1e-6  # cut to room
    assert kept[2] == 0.0  # no room left
    # exited fill frees room: x=11 <= f=12 is observably closed
    kept2 = D.gross_cap_weights(np.array([10, 12]), np.array([11, 200]),
                                np.array([1.0, 1.5]), [0, 1], G=2.0)
    assert kept2[0] == 1.0 and kept2[1] == 1.5


def test_control_ratio_math():
    # S_ctrl_bar = R * S_base_bar with R = N_rule/N_base (pooled that year)
    N_b, N_r, S_b, S_r = 10.0, 8.0, 0.5, 0.45
    R = N_r / N_b
    S_ctrl = R * S_b
    assert abs(R - 0.8) < 1e-12 and abs(S_ctrl - 0.4) < 1e-12
    assert (S_r > S_ctrl) is True  # tilt wins on allocation despite lower exposure
    assert (S_r >= S_b) is False  # ... while losing the raw sum leg


def test_cell_stats_worst_day_dd():
    S, Wd, DD, nd = D.cell_stats_dict(["2021-01-01", "2021-01-01", "2021-01-02"],
                                      [1.0, -0.5, -2.0])
    assert abs(S - (-1.5)) < 1e-12
    assert abs(Wd - (-2.0)) < 1e-12
    assert DD >= 2.0 - 1e-12 and nd == 2
    S0, W0, D0, n0 = D.cell_stats_dict([], [])
    assert (S0, W0, D0, n0) == (0.0, 0.0, 0.0, 0)
