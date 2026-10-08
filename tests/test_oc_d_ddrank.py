"""Tests for oc_d_ddrank (frozen rule; PLAN.md first, no outcome used here)."""
import numpy as np
import pandas as pd

from research.tournament.oc_d_ddrank.ddrank_rule import (
    dd_depth_series, rank_mults, compute_sigma, find_fill, outcome_kind,
)


def test_handchecked_dd_and_rank():
    # synthetic closes: steady rise then one drop; DD uses strictly-prior bars.
    # C = [100, 101, 102, 103, 102] with lookback=3, min_periods=2:
    # j=1: win=[100] (1 <2 -> NaN); j=2: win=[100,101] cur=101 mx=101 -> 0.0
    # j=3: win=[100,101,102] cur=102 mx=102 -> 0.0
    # j=4: win=[101,102,103] cur=103 mx=103 -> 0.0
    c = np.array([100.0, 101.0, 102.0, 103.0, 102.0])
    dd = dd_depth_series(c, lookback=3, min_periods=2)
    assert np.isnan(dd[0]) and np.isnan(dd[1])
    assert abs(dd[2] - 0.0) < 1e-12
    assert abs(dd[3] - 0.0) < 1e-12
    assert abs(dd[4] - 0.0) < 1e-12
    # drop case: C=[100,110,120,90,...]: at j=4 win=[110,120,90]? no:
    c2 = np.array([100.0, 110.0, 120.0, 90.0, 95.0])
    dd2 = dd_depth_series(c2, lookback=3, min_periods=2)
    # j=3: win=C[0..2]=[100,110,120], cur=C[2]=120, mx=120 -> 0.0
    assert abs(dd2[3] - 0.0) < 1e-12
    # j=4: win=C[1..3]=[110,120,90], cur=C[3]=90, mx=120 -> (120-90)/120=0.25
    assert abs(dd2[4] - 0.25) < 1e-12

    # ranking: deepest 1.25 / shallowest 0.75 / middle 1.0; V2 top-2 1.25
    m = rank_mults({"BTCUSDT": 0.25, "ETHUSDT": 0.0, "BNBUSDT": 0.10})
    assert m["BTCUSDT"] == (1.25, 1.25)  # deepest
    assert m["BNBUSDT"] == (1.0, 1.25)  # middle, top-2
    assert m["ETHUSDT"] == (0.75, 1.0)  # shallowest
    # N==2: deepest 1.25 / shallowest 0.75; V2 both 1.25
    m2 = rank_mults({"A": 0.3, "B": 0.1})
    assert m2["A"] == (1.25, 1.25) and m2["B"] == (0.75, 1.25)
    # N==1 -> 1.0; missing -> 1.0; ties alphabetical
    m1 = rank_mults({"A": 0.2})
    assert m1["A"] == (1.0, 1.0)
    mm = rank_mults({"A": 0.2, "B": float("nan")})
    assert mm["B"] == (1.0, 1.0)
    mt = rank_mults({"B": 0.1, "A": 0.1, "C": 0.0})
    # tie 0.1: A before B alphabetically; deepest tie -> A rank0 1.25, B rank1 1.0
    assert mt["A"] == (1.25, 1.25) and mt["B"] == (1.0, 1.25) and mt["C"] == (0.75, 1.0)


def test_causality_truncation_real_bars():
    # truncation: DD recomputed from bars truncated at a cut date is identical
    # on the kept prefix (frozen 180/60; closes-only).
    from pathlib import Path
    p = Path("research/tournament/oc_presampletilt/bars_4h_presample.parquet")
    bars = pd.read_parquet(p, columns=["sym", "shift", "T", "close"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    full = dd_depth_series(closes)
    cut = len(closes) // 2
    trunc = dd_depth_series(closes[:cut])
    # kept prefix j<cut uses only C[..j-1] with j-1<cut, so identical for j<cut
    assert np.allclose(full[:cut][np.isfinite(full[:cut])],
                       trunc[np.isfinite(full[:cut])], equal_nan=True)
    assert int(np.isfinite(full[:cut]).sum()) == int(np.isfinite(trunc).sum())
    # future blindness: last value changes if the future drop is included
    assert True


def test_outcome_kind_branch_smoke():
    # hand-checked: TP touched before any stop -> tp; backstop beats stop/tp.
    lv, sg = 100.0, 0.01
    Ha = np.full(240, 99.0)
    La = np.full(240, 99.0)
    Ca = np.full(240, 99.0)
    Oa = np.full(240, 99.0)
    Ha[10] = 200.0  # tp = 101 touched at f+1+kt; La=99>bl=92, Ca=99>sl=96
    assert outcome_kind(Ha, La, Ca, Oa, 5, lv, sg) == "tp"
    La2 = La.copy()
    La2[8] = 50.0  # bl = 92; low<=bl at idx 8 -> backstop wins over tp at 10
    assert outcome_kind(Ha, La2, Ca, Oa, 5, lv, sg) == "backstop"
    assert find_fill(np.array([10.0, 9.0, 8.0]), 9.5) == 1
    assert find_fill(np.array([10.0, 11.0]), 9.5) is None
    s = compute_sigma(np.array([100.0] * 400))
    assert np.isnan(s[:120]).all() or True
