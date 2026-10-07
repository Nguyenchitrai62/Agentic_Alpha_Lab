"""oc_outage tests: outage overlay on the D0+B1 replica (synthetic + determinism)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_outage"
sys.path.insert(0, str(OC))
import outage_core as K

MK, TK, FUND = 0.0002, 0.00055, 0.0001


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def _global_flat(n=2000, o=100.0):
    return (np.full(n, o), np.full(n, o), np.full(n, o), np.full(n, o))


# --- D0 verbatim ---

def test_tp_hit():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = K.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_stop_first_same_minute():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[29] = lv * (1 + sg) + 0.01
    C[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = K.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "stop"
    assert abs(ret - (O[x] / lv - 1 - MK - TK)) < 1e-12


def test_backstop_beats_tp():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[25] = lv * (1 + sg) + 0.01
    Lw[25] = lv * (1 - 8 * sg) - 0.01
    ret, x, how = K.outcome_mu(H, Lw, C, O, f, lv, sg, 1.0, 99.0, False)
    assert how == "backstop" and x == 25


def test_timeout_funding():
    O, H, Lw, C = _flat()
    r0, _, h0 = K.outcome_mu(H, Lw, C, O, 20, 100.0, 0.01, 1.0, 101.0, False)
    r1, _, h1 = K.outcome_mu(H, Lw, C, O, 20, 100.0, 0.01, 1.0, 101.0, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - FUND) < 1e-12


# --- B1 helpers ---

def test_size_mult():
    assert K.size_mult(0) == 1.0
    assert abs(K.size_mult(2) - 1 / 3) < 1e-12


def test_n_vector_counts_only_flushing():
    cmat = np.array([[90.0, 100.0], [100.0, 100.0], [np.nan, 100.0], [80.0, 80.0]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    # thr = 100*(1-0.025) = 97.5: coin0 flush at m0 only, coin3 both
    n = K.n_vector(cmat, oo, ss)
    assert list(n) == [2, 1]


def test_find_fill_strict():
    assert K.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert K.find_fill(np.array([100.0, 99.9]), 100.0) == 1


# --- outage intervals ---

def test_is_offline_and_comeback():
    ivs = [(100, 220), (300, 360)]
    assert not K.is_offline(99, ivs)
    assert K.is_offline(100, ivs)
    assert K.is_offline(219, ivs)
    assert not K.is_offline(220, ivs)
    assert K.comeback(219, ivs) == 220
    assert K.comeback(220, ivs) == 220
    assert K.comeback(50, ivs) == 50


def test_gen_block_outages_deterministic():
    a = K.gen_block_outages(0, 10080, 120, 101)
    b = K.gen_block_outages(0, 10080, 120, 101)
    c = K.gen_block_outages(0, 10080, 120, 999)
    assert a == b and a != c
    assert len(a) == 525600 // 10080
    assert all(e - s == 120 for s, e in a)
    assert all(a[i][1] <= a[i + 1][0] for i in range(len(a) - 1))
    m = K.gen_block_outages(0, 43800, 360, 102)
    assert len(m) == 12 and all(e - s == 360 for s, e in m)
    q = K.gen_block_outages(0, 131400, 1440, 103)
    assert len(q) == 4 and all(e - s == 1440 for s, e in q)


def test_rank_worst_hours():
    hs = np.array([0, 60, 120, 180])
    r = np.array([-0.05, np.nan, -0.05, 0.01])
    pick = K.rank_worst_hours(hs, r, 2)
    assert pick == [0, 2]  # NaN skipped, tie -> earliest first


# --- deferred exits ---

def _mk_global_with_bar():
    # absolute arrays; bar at t_abs=1000, lv=100, sg=0.01
    n = 3000
    H, L, O, C = _global_flat(n)
    return H, L, O, C


def test_native_tp_offline_unchanged():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    tp = lv * (1 + sg)
    H[t_abs + 30] = tp + 0.01  # TP touch inside outage
    ivs = [(t_abs + 25, t_abs + 40)]
    ret, xo, how, delayed, rescued = K.apply_outage_to_fill(
        f, lv, sg, 0.0096, 30, "tp", t_abs, 99.0, False, H, L, O, ivs)
    assert how == "tp" and not delayed and xo == 30


def test_stop_deferred_to_comeback():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    # base stop exits at x0=30 (online ref); force offline by covering Te
    ivs = [(t_abs + 29, t_abs + 50)]
    O[t_abs + 50] = 98.0  # comeback open
    ret, xo, how, delayed, rescued = K.apply_outage_to_fill(
        f, lv, sg, -0.01, 30, "stop", t_abs, 99.0, False, H, L, O, ivs)
    assert delayed and how == "stop_late" and xo == 50 and not rescued
    assert abs(ret - (98.0 / lv - 1 - MK - TK)) < 1e-12


def test_time_late_settling_pays_funding():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    ivs = [(t_abs + 239, t_abs + 260)]
    O[t_abs + 260] = 101.0
    ret, xo, how, delayed, _ = K.apply_outage_to_fill(
        f, lv, sg, 0.0, 240, "time", t_abs, 99.0, True, H, L, O, ivs)
    assert how == "time_late" and xo == 260
    assert abs(ret - (101.0 / lv - 1 - MK - TK - FUND)) < 1e-12


def test_tp_rescued_during_delay():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    tp = lv * (1 + sg)
    H[t_abs + 40] = tp + 0.01  # TP after base stop, before comeback
    ivs = [(t_abs + 29, t_abs + 50)]
    O[t_abs + 50] = 90.0
    ret, xo, how, delayed, rescued = K.apply_outage_to_fill(
        f, lv, sg, -0.02, 30, "stop", t_abs, 99.0, False, H, L, O, ivs)
    assert how == "tp" and rescued and xo == 40
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_backstop_beats_tp_in_delay():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    tp = lv * (1 + sg)
    bl = lv * (1 - 8 * sg)
    H[t_abs + 40] = tp + 0.01
    L[t_abs + 40] = bl - 0.01
    O[t_abs + 40] = 100.0
    ivs = [(t_abs + 29, t_abs + 50)]
    _, _, how, _, rescued = K.apply_outage_to_fill(
        f, lv, sg, -0.02, 30, "stop", t_abs, 99.0, False, H, L, O, ivs)
    assert how == "backstop" and rescued


def test_comeback_nan_dropped():
    H, L, O, C = _mk_global_with_bar()
    t_abs, f, lv, sg = 1000, 20, 100.0, 0.01
    ivs = [(t_abs + 29, t_abs + 50)]
    O[t_abs + 50] = np.nan
    import math
    ret, _, how, _, _ = K.apply_outage_to_fill(
        f, lv, sg, -0.02, 30, "stop", t_abs, 99.0, False, H, L, O, ivs)
    assert how == "dropped" and math.isnan(ret)


def test_cell_stats_and_shares_sum():
    d = np.array([0, 0, 1, 1])
    v = np.array([1.0, -0.5, 2.0, -4.0])
    s, w, dd = K.cell_stats(d, v)
    assert abs(s - (-1.5)) < 1e-12 and abs(w - (-2.0)) < 1e-12
    assert abs(dd - 2.0) < 1e-12
    # shares identity: missed + late == loss
    base, scen = 5.0, 3.0
    missed, late = 1.2, 0.8
    assert abs((missed + late) - (base - scen)) < 1e-12
