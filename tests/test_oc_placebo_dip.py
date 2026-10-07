"""oc_placebo_dip tests: replica exactness + hash selection + scoring (synthetic)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_placebo_dip"
sys.path.insert(0, str(OC))
import compute_placebo_dip as P

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_outcome_tp_pays_two_makers():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + 1.0 * sg)  # 101
    H[30] = tp + 0.01  # strict touch
    r, x, h = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, False)
    assert h == "tp" and x == 30
    assert abs(r - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_outcome_close5_clock_only():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    m = 21  # (21+1)%5 != 0: not a close5 minute
    assert (m + 1) % 5 != 0
    C[m] = sl - 0.01
    O[m + 1] = 95.0
    r, x, h = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, False)
    assert h == "time" and x == 240
    assert abs(r - (99.0 / lv - 1 - MK - TK)) < 1e-12


def test_outcome_stop_exit_next_open():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    m = 24  # (24+1)%5 == 0
    C[m] = sl - 0.01
    O[m + 1] = 95.0
    r, x, h = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, False)
    assert h == "stop" and x == m + 1
    assert abs(r - (95.0 / lv - 1 - MK - TK)) < 1e-12


def test_outcome_backstop_wins_tie_and_stop_first():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    bl = lv * (1 - 8 * sg)  # 92
    tp = lv * (1 + 1.0 * sg)
    m = 50
    L[m] = bl - 0.5  # backstop touch
    O[m] = 95.0
    H[m] = tp + 1.0  # TP touched same minute -> backstop wins
    r, x, h = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, False)
    assert h == "backstop" and x == m
    assert abs(r - (min(bl, 95.0) / lv - 1 - MK - TK)) < 1e-12
    # stop beats TP in the same minute (use a close5 clock minute m=49)
    O2, H2, L2, C2 = _flat()
    sl = lv * (1 - 4 * sg)
    m2 = 49
    assert (m2 + 1) % 5 == 0
    C2[m2] = sl - 0.01
    H2[m2] = tp + 1.0
    O2[m2 + 1] = 95.0
    r2, x2, h2 = P.outcome_mu(H2, L2, C2, O2, f, lv, sg, 1.0, 99.0, False)
    # TP touch and stop signal share index (kt<ks false: tie) -> stop wins
    assert h2 == "stop" and x2 == m2 + 1


def test_outcome_timeout_funding_only_on_settle():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    r_s, x_s, h_s = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, True)
    r_n, _, _ = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 99.0, False)
    assert h_s == "time" and x_s == 240
    assert abs((r_n - r_s) - P.FUND) < 1e-12


def test_outcome_nan_exit_dropped():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    r, x, h = P.outcome_mu(H, L, C, O, f, lv, sg, 1.0, np.nan, True)
    assert h == "time" and np.isnan(r)


def test_n_vector_boundary_and_nan():
    cmat = np.array([[97.5, 97.51, np.nan],
                     [90.0, 99.0, 97.5],
                     [100.0, 100.0, 100.0],
                     [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    assert P.n_vector(cmat, oo, ss).tolist() == [3, 1, 2]
    assert P.size_mult(0) == 1.0
    assert abs(P.size_mult(4) - 0.2) < 1e-12


def test_find_fill_strict_and_nan():
    assert P.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert P.find_fill(np.array([np.nan, 99.9]), 100.0) == 1
    assert P.find_fill(np.array([np.nan, np.nan]), 100.0) is None


def test_hash_uniform_deterministic_and_sized():
    k = np.array([0, 1, 2, 2**32, 2**63 - 1], dtype=np.uint64)
    u1 = P.hash_uniform(k)
    u2 = P.hash_uniform(k)
    assert u1.shape == (5,) and np.array_equal(u1, u2)
    assert bool(((u1 >= 0.0) & (u1 < 1.0)).all())
    assert len(set(u1.tolist())) == 5  # distinct keys -> distinct draws


def test_hash_selection_return_independent_and_rates():
    # same keys, shuffled returns -> identical selection; rates ~ nominal
    n = 20000
    ph = np.zeros(n, dtype=np.uint64)
    bt = np.arange(n, dtype=np.uint64)
    co = (np.arange(n) % 5).astype(np.uint64)
    ru = (np.arange(n) % 5).astype(np.uint64)
    sel_b = P.hash_uniform(P.fill_key(2, 7, ph, bt, co, ru)) < P.FRAC_B
    assert abs(sel_b.mean() - 0.10) < 0.01
    sel_c = P.hash_uniform(P.fill_key(3, 7, ph, bt, co, ru)) < P.FRAC_C
    assert abs(sel_c.mean() - 0.20) < 0.01
    # different rule -> different selection (seeded per rule)
    sel_b2 = P.hash_uniform(P.fill_key(2, 8, ph, bt, co, ru)) < P.FRAC_B
    assert 0.05 < abs(sel_b ^ sel_b2).mean() < 0.25
    # bar-level: all fills of one bar share the bar draw
    bar_sel = P.hash_uniform(P.bar_key(1, 3, ph, bt)) < 0.15
    assert bar_sel.shape == (n,)
    assert abs(bar_sel.mean() - 0.15) < 0.01


def test_cell_stats_and_decide_criterion():
    s, w, dd = P.cell_stats(np.array([5, 5, 6]), np.array([1.0, -0.4, 0.2]))
    # day5 = 0.6, day6 = 0.2 -> sum 0.8, worst 0.2, path [0.6, 0.8]: no DD
    assert abs(s - 0.8) < 1e-12 and abs(w - 0.2) < 1e-12 and abs(dd) < 1e-12
    s2, w2, dd2 = P.cell_stats(np.array([5, 6, 7]), np.array([1.0, -1.5, 0.2]))
    # cum = [1.0, -0.5, -0.3] -> DD 1.5, worst day -1.5
    assert abs(s2 - (-0.3)) < 1e-12 and abs(w2 - (-1.5)) < 1e-12
    assert abs(dd2 - 1.5) < 1e-12
    base = {"per_year": [{"S": 1.0, "DD": 0.5} for _ in range(5)],
            "sum5y": 5.0, "ddmean": 0.5, "full_dd": 0.5}
    rule = {"per_year": [{"S": 1.1, "DD": 0.5} for _ in range(4)]
            + [{"S": 0.9, "DD": 0.5}],
            "sum5y": 5.3, "ddmean": 0.5, "full_dd": 0.5}
    d = P.decide(rule, base)
    assert d["years_sum_ge"] == 4 and d["years_dd_ok"] == 5
    assert d["pass_sum_half"] and d["promising"]
    assert abs(d["dSum5y"] - 0.3) < 1e-12
    # DD worse by exactly the 1pp tolerance still passes
    rule2 = {"per_year": [{"S": 1.1, "DD": 0.51} for _ in range(5)],
             "sum5y": 5.5, "ddmean": 0.51, "full_dd": 0.51}
    d2 = P.decide(rule2, base)
    assert d2["years_dd_ok"] == 5 and d2["promising"]
    rule3 = {"per_year": [{"S": 1.1, "DD": 0.510001} for _ in range(5)],
             "sum5y": 5.5, "ddmean": 0.510001, "full_dd": 0.510001}
    d3 = P.decide(rule3, base)
    assert d3["years_dd_ok"] == 0 and not d3["promising"]


def test_score_assignment_groups_phases_years():
    led = {"phase": np.array([0, 1, 0, 1, 2]),
           "year": np.array([0, 0, 0, 0, 0]),
           "w": np.ones(5), "y10": np.ones(5),
           "d10": np.array([10, 10, 11, 11, 12])}
    sc = P.score_assignment(led["phase"], led["year"], led["w"], led["y10"], led["d10"])
    assert abs(sc["per_year"][0]["S"] - 1.25) < 1e-12  # mean over 4 phases
    assert abs(sc["sum5y"] - 1.25) < 1e-12
    assert abs(sc["full_sum"] - 5.0) < 1e-12
