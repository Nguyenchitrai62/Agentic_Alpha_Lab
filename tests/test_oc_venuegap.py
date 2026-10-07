"""oc_venuegap tests: synthetic hand checks + causality guards (no big data)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path("research/tournament/oc_venuegap")
sys.path.insert(0, str(HERE))
import venue as V
import run as R


def test_n_vector_exact_threshold_counts():
    o = np.array([100.0])
    sg = np.array([0.01])  # thr = 100*(1-0.025) = 97.5
    c = np.array([[97.5, 97.6, np.nan]])
    n = V.n_vector(c, o, sg)
    assert list(n) == [1, 0, 0]


def test_n_vector_nan_open_or_sigma_skips():
    c = np.array([[50.0]])
    assert list(V.n_vector(c, np.array([np.nan]), np.array([0.01]))) == [0]
    assert list(V.n_vector(c, np.array([100.0]), np.array([np.nan]))) == [0]
    assert list(V.n_vector(c, np.array([100.0]), np.array([0.0]))) == [0]


def test_find_fill_strict():
    assert V.find_fill(np.array([10.0, 9.0]), 9.0) is None  # equal != fill
    assert V.find_fill(np.array([9.0, 8.999, 8.0]), 9.0) == 1
    assert V.find_fill(np.array([np.nan, np.nan]), 9.0) is None


def test_outcome_tp_net():
    px, sg = 100.0, 0.01
    tp = px * (1 + sg)
    n = 240
    Ha = np.full(n, tp * 1.01)  # high > tp immediately after fill
    La = np.full(n, px * 0.999)  # never near backstop
    Ca = np.full(n, px)  # never at close-stop
    Oa = np.full(n, px)
    ret, x, how = V.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False)
    assert how == "tp"
    assert abs(ret - (tp / px - 1 - 2 * V.MAKER)) < 1e-12


def test_outcome_stop_first_wins_tie():
    px, sg = 100.0, 0.01
    bl = px * (1 - 8 * sg)
    tp = px * (1 + sg)
    n = 240
    Ha = np.full(n, px)  # highs: only minute 17 spikes above tp
    Ha[17] = tp * 1.01
    La = np.full(n, px)
    La[17] = bl - 1.0  # same minute touches backstop -> stop wins
    Ca = np.full(n, px)
    Oa = np.full(n, px)
    ret, x, how = V.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False)
    assert how == "backstop"
    assert x == 17


def test_sigma_excludes_current_bar():
    # flat opens then a jump at the last bar: sigma at last bar must not see it
    ob = np.array([100.0] * 361 + [200.0])
    sg = R.bar_sigmas(ob)
    assert sg[-1] == 0.0  # prior 360 returns are all zero


def test_year_of_exit_boundaries():
    assert R.year_of_exit(pd.Timestamp("2021-11-15", tz="UTC")) == 0
    assert R.year_of_exit(pd.Timestamp("2022-09-24 00:00", tz="UTC")) == 0
    assert R.year_of_exit(pd.Timestamp("2022-09-24 00:01", tz="UTC")) == 1
    # leap-day gap joins year 3
    assert R.year_of_exit(pd.Timestamp("2024-09-23 12:00", tz="UTC")) == 3
    # after the final window joins year 4
    assert R.year_of_exit(pd.Timestamp("2026-09-24 01:00", tz="UTC")) == 4
    assert R.year_of_exit(pd.Timestamp("2021-09-24 00:00", tz="UTC")) is None


def test_overlap_and_cap_constants():
    assert R.OVERLAP_START == pd.Timestamp("2021-11-15 00:00", tz="UTC")  # S5 start
    assert R.END == pd.Timestamp("2026-09-24 00:00", tz="UTC")
    assert R.BYB_DIR == Path("data/raw/bybit_linear_1m_20261004")  # S5 store


def test_bybit_ms_timebase():
    t = pd.to_datetime(1634256000000, unit="ms", utc=True)
    assert t == pd.Timestamp("2021-10-15 00:00:00", tz="UTC")  # SOL first bar


def test_cost_constants_match_b1_replica():
    assert (V.MAKER, V.TAKER, V.FUND) == (0.0002, 0.00055, 0.0001)
    assert tuple(V.RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)
    assert (V.LIVE_A, V.LIVE_B) == (16, 238)
