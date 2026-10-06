"""oc_bidttl tests: TTL window, D0 exit, B1 size, G-cap walk, scoring (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_bidttl"
sys.path.insert(0, str(OC))
import bidttl as B


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_ttl_window_boundary():
    # live base 16..238, TTL 16..135: fill at 135 kept, at 136 lost
    assert B.LIVE_A == 16 and B.LIVE_B == 238 and B.TTL_B == 135
    assert (B.TTL_B - B.LIVE_A + 1) == 120
    low = np.full(B.LIVE_B - B.LIVE_A + 1, 100.0)
    low[135 - B.LIVE_A] = 90.0  # offset 135
    assert B.find_fill(low, 95.0) == 135 - B.LIVE_A
    low2 = np.full(B.LIVE_B - B.LIVE_A + 1, 100.0)
    low2[136 - B.LIVE_A] = 90.0  # offset 136
    f = B.LIVE_A + B.find_fill(low2, 95.0)
    assert f == 136 and f > B.TTL_B  # TTL cancels this


def test_fill_strict_trade_through():
    low = np.full(223, 100.0)
    low[5] = 95.0  # equal level never fills
    assert B.find_fill(low, 95.0) is None
    low[5] = 94.999
    assert B.find_fill(low, 95.0) == 5
    low_nan = np.full(223, np.nan)
    assert B.find_fill(low_nan, 95.0) is None


def test_n_exact_boundary_and_nan():
    cmat = np.array([[97.5, 97.51, np.nan]])
    oo = np.array([100.0])
    ss = np.array([0.01])
    n = B.n_vector(cmat, oo, ss)
    assert n.tolist() == [1, 0, 0]  # exact 97.5 counts; NaN never counts
    assert B.size_mult(0) == 1.0
    assert abs(B.size_mult(3) - 0.25) < 1e-12


def test_d0_tp_and_stop_first():
    O, H, L, C = _flat()
    lv, sg, o2 = 100.0, 0.01, 100.0
    # TP at 101 touched strictly
    H[60] = 101.01
    ret, x, how = B.outcome_from_fill(H, L, C, O, 50, lv, sg, o2, False)
    assert how == "tp" and x == 60
    assert abs(ret - (101.0 / 100 - 1 - 2 * 0.0002)) < 1e-12
    # same-minute stop+TP -> stop wins
    O2, H2, L2, C2 = _flat()
    sl = lv * (1 - 4 * sg)  # 96
    H2[70] = 102.0
    C2[69] = sl - 0.01  # clock minute 69 ((69+1)%5==0) triggers close5 stop
    ret2, x2, how2 = B.outcome_from_fill(H2, L2, C2, O2, 50, lv, sg, o2, False)
    assert how2 == "stop"


def test_d0_backstop_priority_and_funding():
    O, H, L, C = _flat()
    lv, sg = 100.0, 0.01
    L[60] = 90.0  # bl = 92 touched
    H[60] = 105.0  # TP also touched same minute -> backstop wins
    ret, x, how = B.outcome_from_fill(H, L, C, O, 50, lv, sg, 100.0, False)
    assert how == "backstop"
    # timeout funding: settle True charges 0.0001
    O3, H3, L3, C3 = _flat()
    r0, _, h0 = B.outcome_from_fill(H3, L3, C3, O3, 50, lv, sg, 100.0, False)
    r1, _, h1 = B.outcome_from_fill(H3, L3, C3, O3, 50, lv, sg, 100.0, True)
    assert h0 == "time" and h1 == "time"
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_cap_walk_cut_skip_order():
    # order (f,k,coin): second fill cut to room, third skipped when full
    f = np.array([10, 11, 12])
    x = np.array([200, 200, 200])
    w = np.array([1.0, 1.5, 1.0])
    kept = B.gross_cap_weights(f, x, w, [0, 1, 2], G=2.0)
    assert kept[0] == 1.0
    assert abs(kept[1] - 1.0) < 1e-12  # cut to room
    assert kept[2] == 0.0  # no room
    # exited fill frees room: x=11 <= f=12 is closed
    kept2 = B.gross_cap_weights(np.array([10, 12]), np.array([11, 200]),
                                np.array([1.0, 1.5]), [0, 1], G=2.0)
    assert kept2[0] == 1.0 and kept2[1] == 1.5


def test_cell_stats_worst_day_dd():
    S, Wd, DD, nd = B.cell_stats_dict(["2021-01-01", "2021-01-01", "2021-01-02"],
                                      [1.0, -0.5, -2.0])
    assert abs(S - (-1.5)) < 1e-12
    assert abs(Wd - (-2.0)) < 1e-12
    assert DD >= 2.0 - 1e-12 and nd == 2
    S0, W0, D0, n0 = B.cell_stats_dict([], [])
    assert (S0, W0, D0, n0) == (0.0, 0.0, 0.0, 0)
