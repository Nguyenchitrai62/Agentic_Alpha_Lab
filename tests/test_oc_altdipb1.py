"""Tests for oc_altdipb1 (8-coin dip replica + alt sleeve).

Lightweight: synthetic hand checks + causality/truncation + results-file
consistency. No 1m data reads.
"""
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
MOD = ROOT / "research/tournament/oc_altdipb1/compute_altdipb1.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_altdipb1", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()


def test_size_mult_b1():
    assert M.size_mult(0) == 1.0
    assert abs(M.size_mult(1) - 0.5) < 1e-12
    assert abs(M.size_mult(7) - 1 / 8) < 1e-12


def test_find_fill_strict_trade_through():
    low = np.array([100.0, 99.0, 98.0])
    assert M.find_fill(low, 99.0) == 2  # equal is NOT a fill
    assert M.find_fill(low, 99.5) == 1
    assert M.find_fill(low, 90.0) is None


def test_n_vector_nan_never_counts_and_le_counts():
    # one other coin: O=100, sg=0.01 -> thr=97.5; C series over window
    close = np.array([[98.0, 97.5, np.nan, 90.0]])
    n = M.n_vector(close, np.array([100.0]), np.array([0.01]))
    assert n.tolist() == [0, 1, 0, 1]


def test_n_vector_causality_window_alignment():
    # window C[b][base+15 : base+223] aligns with live offsets 16..238
    # (C at T+m-1, last fully closed minute); check helper length contract
    W = M.LIVE_B - M.LIVE_A + 1
    assert W == 223
    close = np.full((7, W), 100.0)
    n = M.n_vector(close, np.full(7, 100.0), np.full(7, 0.01))
    assert (n == 0).all()  # nothing flushing -> n = 0, own coin never counted


def test_outcome_tp_hand_checked():
    # lv=100, sg=0.01, mu=1 -> tp=101, sl=96, bl=92; f=16
    lv, sg, f = 100.0, 0.01, 16
    H = np.full(240, 100.0)
    L = np.full(240, 100.0)
    C = np.full(240, 100.0)
    O = np.full(240, 100.0)
    H[f + 1] = 101.5  # strict TP touch at first post-fill minute
    L[f + 1] = 100.5
    C[f + 1] = 101.2
    ret, x, how = M.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "tp" and x == f + 1
    assert abs(ret - (101.0 / 100.0 - 1 - 2 * M.MAKER)) < 1e-12  # 0.0096


def test_outcome_stop_first_same_minute():
    # same minute t: low <= bl (backstop) and high > tp -> backstop wins
    lv, sg, f = 100.0, 0.01, 16
    H = np.full(240, 100.0)
    L = np.full(240, 100.0)
    C = np.full(240, 100.0)
    O = np.full(240, 100.0)
    H[f + 1] = 102.0
    L[f + 1] = 91.0  # <= bl=92
    ret, x, how = M.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "backstop" and x == f + 1
    # gap pays the open: min(bl, open)=min(92,100)=92
    assert abs(ret - (92.0 / 100.0 - 1 - M.MAKER - M.TAKER)) < 1e-12


def test_outcome_close5_stop_uses_next_open_taker():
    lv, sg, f = 100.0, 0.01, 16
    H = np.full(240, 100.0)
    L = np.full(240, 100.0)
    C = np.full(240, 100.0)
    O = np.full(240, 100.0)
    # first clock minute m with (m+1)%5==0 after f is m=19; close <= sl=96
    C[19] = 95.0
    O[20] = 95.5
    ret, x, how = M.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 100.0, False)
    assert how == "stop" and x == 20
    assert abs(ret - (95.5 / 100.0 - 1 - M.MAKER - M.TAKER)) < 1e-12


def test_year_of_boundaries():
    import pandas as pd
    assert M.year_of(pd.Timestamp("2021-09-24", tz="UTC")) == 0
    assert M.year_of(pd.Timestamp("2025-09-24", tz="UTC")) == 4
    assert M.year_of(pd.Timestamp("2026-09-24", tz="UTC")) is None
    assert M.year_of(pd.Timestamp("2021-09-23 23:59", tz="UTC")) is None


def test_truncation_bars_outside_window_excluded():
    # bars with open outside [2021-09-24, 2026-09-24) map to no year
    import pandas as pd
    assert M.year_of(pd.Timestamp("2020-08-01", tz="UTC")) is None
    assert M.year_of(pd.Timestamp("2026-09-25", tz="UTC")) is None


def test_pearson_corr_identity_and_flat():
    d = np.array([1, 2, 3])
    assert abs(M.pearson_corr(d, np.array([1.0, 2.0, 3.0]),
                              d, np.array([1.0, 2.0, 3.0])) - 1.0) < 1e-12
    assert not np.isfinite(M.pearson_corr(d, np.array([1.0, 1.0, 1.0]),
                                          d, np.array([1.0, 2.0, 3.0])))


def test_results_file_consistency():
    res = json.loads((ROOT / "research/tournament/oc_altdipb1/results.json").read_text())
    assert abs(res["MAJORS_sum5y"] - 7.718304) < 0.02  # placebo replica gate
    assert res["n_fills"]["MAJORS"] == 22312
    assert res["n_fills"]["ALT8"] == res["n_fills"]["MAJORS"] + res["n_fills"]["ALT3"]
    # ALT8 = majors-leg + ALT3 by construction
    assert abs(res["ALT8_sum5y"]
               - (res["majors_leg_of_ALT8_sum5y"] + res["ALT3_sum5y"])) < 1e-6
    g = res["gate"]
    assert g["years_sum_ge"] == 5 and g["years_dd_ok"] == 0
    assert g["show_to_owner"] is False
    assert abs(g["dSum5y_ALT8_minus_MAJORS"] - 1.950227) < 1e-3
    # alt coverage predates the test window (listing-date check)
    cov = res["config"]["alt_coverage_manifest"]
    assert set(cov) == {"DOGEUSDT", "ADAUSDT", "TRXUSDT"}
    import pandas as pd
    for sym, c in cov.items():
        assert pd.Timestamp(c["first"]) < pd.Timestamp("2021-09-24", tz="UTC")
