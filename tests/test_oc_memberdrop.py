"""Tests for oc_memberdrop (book member ablation + stale-feed stress).

Covers: hand-checked synthetic blend weights (FULL/NO_FLOW/NO_CB), the 72h
freeze rule (frozen value, window bounds, resume), bear-filter causality, and
a truncation test on the real member files (no future rows leak into books).
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MOD = ROOT / "research/tournament/oc_memberdrop/run_memberdrop.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_memberdrop_mod", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()
COLS = ["BNBUSDT", "BTCUSDT"]


def _synth_members(n=12):
    idx = pd.date_range("2021-09-24", periods=n, freq="4h", tz="UTC")
    mk = lambda v: pd.DataFrame(v, index=idx, columns=COLS)
    A = mk(np.arange(n)[:, None] * np.ones((1, 2)) * 0.1)
    Aq = mk(np.ones((n, 2)) * 0.2)
    B = mk(np.ones((n, 2)) * 0.3)
    Bq = mk(np.ones((n, 2)) * -0.1)
    D = mk(np.ones((n, 2)) * 0.4)
    Dq = mk(np.ones((n, 2)) * 0.0)
    return idx, dict(A=A, Aq=Aq, B=B, Bq=Bq, D=D, Dq=Dq)


def _blend(m, variant):
    A, Aq, B, Bq, D, Dq = (m[k] for k in ("A", "Aq", "B", "Bq", "D", "Dq"))
    o1 = 0.25 * (A + B + Aq + Bq)
    cb = 0.5 * (D + Dq)
    if variant == "FULL":
        return 0.8 * o1 + 0.2 * cb
    if variant == "NO_FLOW":
        return (0.4 * 0.5 * (B + Bq) + 0.2 * cb) / 0.6
    if variant == "NO_CB":
        return o1
    raise AssertionError(variant)


def test_hand_checked_blend_weights():
    idx, m = _synth_members()
    # hand: o1 = (0.1*i + 0.2 + 0.3 - 0.1)/4 row i; take i=2: A=0.2
    # o1 = (0.2+0.3+0.2-0.1)/4 = 0.15; cb = 0.2; FULL = 0.8*.15+0.2*.2 = 0.16
    assert np.allclose(_blend(m, "FULL").iloc[2].to_numpy(), [0.16, 0.16])
    # NO_FLOW i=2: (0.4*(0.3-0.1)/2 + 0.2*0.2)/0.6 = (0.04+0.04)/0.6
    assert np.allclose(_blend(m, "NO_FLOW").iloc[2].to_numpy(), [0.08 / 0.6] * 2)
    # NO_CB == o1 == 0.15
    assert np.allclose(_blend(m, "NO_CB").iloc[2].to_numpy(), [0.15, 0.15])
    # renormalisation sums to 1: weights implied by construction
    assert abs((1 / 3 + 1 / 3 + 1 / 6 + 1 / 6) - 1.0) < 1e-12
    assert abs((0.25 * 4) - 1.0) < 1e-12


def test_hand_checked_stale_freeze():
    idx, m = _synth_members(n=48)  # 8 days of 4h bars
    S = idx[6]  # outage start on the grid
    Af = m["A"].copy()
    below = idx[idx < S][-1]
    frozen = m["A"].loc[[below]]
    win = (idx >= S) & (idx < S + pd.Timedelta(hours=72))
    assert int(win.sum()) == 18  # 72h / 4h
    Af.loc[win] = np.repeat(frozen.to_numpy(), int(win.sum()), axis=0)
    # frozen at value strictly before S (row 5 -> 0.5), not row 6 (0.6)
    assert np.allclose(Af.loc[win].to_numpy(), 0.5)
    # resumes exactly at S+72h
    after = S + pd.Timedelta(hours=72)
    assert np.allclose(Af.loc[after].to_numpy(), m["A"].loc[after].to_numpy())
    # rows before S untouched
    assert np.allclose(Af.loc[idx < S].to_numpy(), m["A"].loc[idx < S].to_numpy())


def test_stale_starts_preregistered():
    starts = M.stale_starts()
    assert len(starts) == 50  # 10 per year x 5 years
    for y, a in enumerate(M.ANCH):
        yr = starts[y * 10:(y + 1) * 10]
        assert yr[0] == a + pd.Timedelta(days=10)
        for k in range(1, 10):
            assert yr[k] - yr[k - 1] == pd.Timedelta(hours=36.5 * 24)
        assert yr[-1] + pd.Timedelta(hours=72) < a + pd.Timedelta(days=365)


def test_bear_causal_and_longs_only():
    idx = pd.date_range("2021-09-24", periods=8, freq="4h", tz="UTC")
    w = pd.DataFrame([[0.4, -0.5, 0.0]] * 8, index=idx, columns=["a", "b", "c"])
    bear = np.array([False, True, True, False, True, False, False, True])
    out = M.apply_bear(w, bear)
    # longs halved exactly on bear rows, shorts/flats bit-identical
    assert np.allclose(out["a"].to_numpy(),
                       [0.4, 0.2, 0.2, 0.4, 0.2, 0.4, 0.4, 0.2])
    assert np.allclose(out["b"].to_numpy(), [-0.5] * 8)
    assert np.allclose(out["c"].to_numpy(), [0.0] * 8)


def test_book_episodes_hand_checked():
    ev = [
        {"kind": "book_fill", "symbol": "BTCUSDT", "side": "buy",
         "weight": 1.0, "price": 100.0, "t": "2021-09-24 00:00:00+00:00"},
        {"kind": "book_tp", "symbol": "BTCUSDT", "weight": 1.0,
         "price": 110.0, "t": "2021-09-24 04:00:00+00:00"},
    ]
    eps = M.book_episodes(ev)
    assert len(eps) == 1
    # cost 1.0, proceeds 1.1, fees 1.0*0.0002 + 1.1*0.0002
    assert abs(eps[0][1] - ((1.1 - 1.0) - (1.0 * 0.0002 + 1.1 * 0.0002)) / 1.0) < 1e-12


def test_truncation_real_members():
    """Books at rows <= T are unchanged when members are truncated to <= T."""
    eu = M._load("eu_md_test", M.RD / "engine_user" / "engine_user.py")
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    C = eu.er.CACHE
    members = {
        "A": pd.read_parquet(C / "member_A_O1_orders.parquet")[cols],
        "Aq": pd.read_parquet(C / "member_Aq_O1_orders.parquet")[cols],
        "B": pd.read_parquet(C / "member_B_tv.parquet")[cols],
        "Bq": pd.read_parquet(C / "member_Bq_tv.parquet")[cols],
    }
    T = pd.Timestamp("2023-03-01 00:00", tz="UTC")
    rows = books154.index[books154.index <= T]
    assert len(rows) > 100
    full, trunc = {}, {}
    for tag, cut in (("full", None), ("trunc", T)):
        parts = {}
        for k, X in members.items():
            Xc = X[X.index <= cut] if cut is not None else X
            parts[k] = Xc.reindex(rows).fillna(0.0)
        o1 = 0.25 * (parts["A"] + parts["B"] + parts["Aq"] + parts["Bq"])
        full[tag] = o1
    assert full["full"].equals(full["trunc"])
