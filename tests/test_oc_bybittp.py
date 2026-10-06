"""oc_bybittp tests: synthetic hand checks + causality guards (no big data)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path("research/tournament/oc_bybittp")
sys.path.insert(0, str(HERE))
import core as C
import run as R


def test_n_vector_exact_threshold_counts():
    o = np.array([100.0])
    sg = np.array([0.01])  # thr = 100*(1-0.025) = 97.5
    c = np.array([[97.5, 97.6, np.nan]])
    n = C.n_vector(c, o, sg)
    assert list(n) == [1, 0, 0]


def test_n_vector_nan_open_or_sigma_skips():
    c = np.array([[50.0]])
    assert list(C.n_vector(c, np.array([np.nan]), np.array([0.01]))) == [0]
    assert list(C.n_vector(c, np.array([100.0]), np.array([np.nan]))) == [0]
    assert list(C.n_vector(c, np.array([100.0]), np.array([0.0]))) == [0]


def test_find_fill_strict():
    assert C.find_fill(np.array([10.0, 9.0]), 9.0) is None  # equal != fill
    assert C.find_fill(np.array([9.0, 8.999, 8.0]), 9.0) == 1
    assert C.find_fill(np.array([np.nan, np.nan]), 9.0) is None


def test_outcome_tp_net():
    px, sg = 100.0, 0.01
    tp = px * (1 + sg)
    n = 240
    Ha = np.full(n, tp * 1.01)
    La = np.full(n, px * 0.999)
    Ca = np.full(n, px)
    Oa = np.full(n, px)
    ret, x, how = C.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False)
    assert how == "tp"
    assert abs(ret - (tp / px - 1 - 2 * C.MAKER)) < 1e-12


def test_outcome_stop_first_wins_tie():
    px, sg = 100.0, 0.01
    bl = px * (1 - 8 * sg)
    tp = px * (1 + sg)
    n = 240
    Ha = np.full(n, px)
    Ha[17] = tp * 1.01
    La = np.full(n, px)
    La[17] = bl - 1.0  # same minute touches backstop -> stop wins
    Ca = np.full(n, px)
    Oa = np.full(n, px)
    ret, x, how = C.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False)
    assert how == "backstop"
    assert x == 17


def test_miss_bps_sign():
    px, sg = 100.0, 0.01
    tp = C.tp_for(px, sg, 0.0)
    n = 240
    Ha = np.full(n, tp * 0.999)  # 10 bps short
    assert abs(C.max_high_miss_bps(Ha, 16, tp) - 10.0) < 0.02
    Ha2 = np.full(n, tp * 1.001)  # exceeded -> negative miss
    assert C.max_high_miss_bps(Ha2, 16, tp) < 0
    Ha3 = np.full(n, np.nan)
    assert not np.isfinite(C.max_high_miss_bps(Ha3, 16, tp))


def test_tighter_tp_monotone_recovery():
    # tape whose max high sits 3 bps under base TP: d=1,2 miss, d=3,5 hit
    px, sg = 100.0, 0.01
    tp = C.tp_for(px, sg, 0.0)
    n = 240
    Ha = np.full(n, tp * (1 - 3 / 1e4) + 1e-9)
    Ha[20] = tp * (1 - 3 / 1e4)  # peak 3 bps short of base TP
    La = np.full(n, px * 0.999)
    Ca = np.full(n, px)
    Oa = np.full(n, px)
    hows = []
    for d in (0, 1, 2, 3, 5):
        _, _, h = C.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False,
                                      1 - d / 1e4)
        hows.append(h)
    assert hows[0] == "time"  # base TP missed -> timeout
    assert hows[1] == "time" and hows[2] == "time"
    assert hows[3] == "tp" and hows[4] == "tp"  # tighter TP recovers
    # tighter TP costs less per TP than base: shave is negative and grows with d
    r3, _, _ = C.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False, 1 - 3 / 1e4)
    r5, _, _ = C.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False, 1 - 5 / 1e4)
    assert r5 < r3


def test_sigma_excludes_current_bar():
    ob = np.array([100.0] * 361 + [200.0])
    sg = R.bar_sigmas(ob)
    assert sg[-1] == 0.0  # prior 360 returns are all zero


def test_year_of_exit_boundaries():
    assert R.year_of_exit(pd.Timestamp("2021-11-15", tz="UTC")) == 0
    assert R.year_of_exit(pd.Timestamp("2022-09-24 00:00", tz="UTC")) == 0
    assert R.year_of_exit(pd.Timestamp("2022-09-24 00:01", tz="UTC")) == 1
    assert R.year_of_exit(pd.Timestamp("2024-09-23 12:00", tz="UTC")) == 3
    assert R.year_of_exit(pd.Timestamp("2026-09-24 01:00", tz="UTC")) == 4
    assert R.year_of_exit(pd.Timestamp("2021-09-24 00:00", tz="UTC")) is None


def test_overlap_and_cap_constants():
    assert R.OVERLAP_START == pd.Timestamp("2021-11-15 00:00", tz="UTC")  # S5 start
    assert R.END == pd.Timestamp("2026-09-24 00:00", tz="UTC")
    assert R.BYB_DIR == Path("data/raw/bybit_linear_1m_20261004")  # S5 store
    assert tuple(R.OFFSETS) == (1, 2, 3, 5)


def test_cost_constants_match_b1_replica():
    assert (C.MAKER, C.TAKER, C.FUND) == (0.0002, 0.00055, 0.0001)
    assert tuple(C.RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)
    assert (C.LIVE_A, C.LIVE_B) == (16, 238)
