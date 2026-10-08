"""Tests for oc_memberagree (member-agreement confidence sizing, IDEAS8 #3).

Covers: hand-checked synthetic agreement/scale cases (V1 5/3 + V2 6/4
thresholds, ensemble-zero and member-zero edges), bear-filter longs-only,
and a truncation test on the real member files (no future rows leak).
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MOD = ROOT / "research/tournament/oc_memberagree/run_memberagree.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_memberagree_mod", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()


def _frame(idx, cols, vals):
    return pd.DataFrame(vals, index=idx, columns=cols)


def test_hand_checked_agreement_scales():
    idx = pd.date_range("2021-09-24", periods=3, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    # row0: w_ens>0, all 6 members >0 -> a=6 -> V1 1.0, V2 1.0
    # row1: w_ens>0, 4 members >0, 2 members <0 -> a=4 -> V1 0.75, V2 0.5
    # row2: w_ens>0, 2 members >0, 4 members <0 -> a=2 -> V1 0.5, V2 0.5
    w = _frame(idx, cols, [[1.0], [1.0], [1.0]])
    pos = _frame(idx, cols, [[0.5], [0.5], [0.5]])
    neg = _frame(idx, cols, [[-0.5], [-0.5], [-0.5]])
    members = {
        "A": _frame(idx, cols, [[0.5], [0.5], [0.5]]),
        "Aq": _frame(idx, cols, [[0.5], [0.5], [0.5]]),
        "B": _frame(idx, cols, [[0.5], [0.5], [-0.5]]),
        "Bq": _frame(idx, cols, [[0.5], [0.5], [-0.5]]),
        "D": _frame(idx, cols, [[0.5], [-0.5], [-0.5]]),
        "Dq": _frame(idx, cols, [[0.5], [-0.5], [-0.5]]),
    }
    a, s1, s2 = M.agreement_and_scales(members, w)
    assert a["BTCUSDT"].tolist() == [6, 4, 2]
    assert s1["BTCUSDT"].tolist() == [1.0, 0.75, 0.5]
    assert s2["BTCUSDT"].tolist() == [1.0, 0.5, 0.5]
    # boundary a==5 -> V1 1.0, V2 0.75; a==3 -> both 0.5
    w1 = _frame(idx[:1], cols, [[1.0]])
    m5 = dict(members)
    for k in ("A", "Aq", "B", "Bq", "D"):
        m5[k] = _frame(idx[:1], cols, [[0.5]])
    m5["Dq"] = _frame(idx[:1], cols, [[-0.5]])
    a5, s15, s25 = M.agreement_and_scales(m5, w1)
    assert a5["BTCUSDT"].tolist() == [5]
    assert s15["BTCUSDT"].tolist() == [1.0]
    assert s25["BTCUSDT"].tolist() == [0.75]
    m3 = dict(m5)
    for k in ("B", "Bq", "D"):
        m3[k] = _frame(idx[:1], cols, [[-0.5]])
    # now A,Aq agree, rest disagree -> a=2? build a==3: A,Aq,B agree
    m3["B"] = _frame(idx[:1], cols, [[0.5]])
    a3, s13, s23 = M.agreement_and_scales(m3, w1)
    assert a3["BTCUSDT"].tolist() == [3]
    assert s13["BTCUSDT"].tolist() == [0.5]
    assert s23["BTCUSDT"].tolist() == [0.5]


def test_hand_checked_zero_edges():
    idx = pd.date_range("2021-09-24", periods=2, freq="4h", tz="UTC")
    cols = ["ETHUSDT"]
    # ensemble == 0 -> a=6, scales 1.0 (weight stays 0)
    w = _frame(idx, cols, [[0.0], [1.0]])
    members = {k: _frame(idx, cols, [[0.5], [0.0]]) for k in ("A", "Aq", "B", "Bq", "D", "Dq")}
    a, s1, s2 = M.agreement_and_scales(members, w)
    assert a["ETHUSDT"].tolist() == [6, 0]
    # row1: w>0 but every member == 0 -> all disagree -> a=0 -> 0.5/0.5
    assert s1["ETHUSDT"].tolist() == [1.0, 0.5]
    assert s2["ETHUSDT"].tolist() == [1.0, 0.5]


def test_bear_longs_only():
    idx = pd.date_range("2021-09-24", periods=4, freq="4h", tz="UTC")
    w = pd.DataFrame([[0.4, -0.5]] * 4, index=idx, columns=["a", "b"])
    bear = np.array([False, True, True, False])
    out = M.apply_bear(w, bear)
    assert np.allclose(out["a"].to_numpy(), [0.4, 0.2, 0.2, 0.4])
    assert np.allclose(out["b"].to_numpy(), [-0.5] * 4)


def test_book_episode_fee_split_hand_checked():
    ev = [
        {"kind": "book_fill", "symbol": "BTCUSDT", "side": "buy",
         "weight": 1.0, "price": 100.0, "t": "2021-09-24 00:00:00+00:00"},
        {"kind": "book_tp", "symbol": "BTCUSDT", "weight": 1.0,
         "price": 110.0, "t": "2021-09-24 04:00:00+00:00"},
    ]
    eps = M.book_episodes(ev)
    assert len(eps) == 1
    t, net, mf, tf = eps[0]
    assert abs(mf - (1.0 * 0.0002 + 1.1 * 0.0002)) < 1e-12
    assert tf == 0.0
    ev2 = [
        {"kind": "book_fill", "symbol": "ETHUSDT", "side": "sell",
         "weight": 1.0, "price": 100.0, "t": "2021-09-24 00:00:00+00:00"},
        {"kind": "book_stop", "symbol": "ETHUSDT", "weight": 1.0,
         "price": 90.0, "t": "2021-09-24 04:00:00+00:00"},
    ]
    eps2 = M.book_episodes(ev2)
    assert len(eps2) == 1
    assert abs(eps2[0][2] - 1.0 * 0.0002) < 1e-12
    # stop leg: qty 0.01 x price 90 = 0.9 notional x taker
    assert abs(eps2[0][3] - 0.9 * 0.00055) < 1e-12


def test_truncation_real_members():
    """Agreement/scales at rows <= T unchanged when members truncated to <= T."""
    eu = M._load("eu_ma_test", M.RD / "engine_user" / "engine_user.py")
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    Cc = eu.er.CACHE
    T = pd.Timestamp("2023-03-01 00:00", tz="UTC")
    rows = books154.index[books154.index <= T]
    assert len(rows) > 100
    files = {"A": "member_A_O1_orders.parquet", "Aq": "member_Aq_O1_orders.parquet",
             "B": "member_B_tv.parquet", "Bq": "member_Bq_tv.parquet"}
    full, trunc = {}, {}
    for tag, cut in (("full", None), ("trunc", T)):
        parts = {}
        for k, fn in files.items():
            X = pd.read_parquet(Cc / fn)[cols]
            if cut is not None:
                X = X[X.index <= cut]
            parts[k] = X.reindex(rows).fillna(0.0)
        D = pd.read_parquet(Cc / "members_v154.parquet").xs("D", axis=1, level=0)[cols]
        Dq = pd.read_parquet(Cc / "members_quarterly_D.parquet")[cols]
        if cut is not None:
            D, Dq = D[D.index <= cut], Dq[Dq.index <= cut]
        parts["D"] = D.reindex(rows).fillna(0.0)
        parts["Dq"] = Dq.reindex(rows).fillna(0.0)
        o1 = 0.25 * (parts["A"] + parts["B"] + parts["Aq"] + parts["Bq"])
        w = 0.8 * o1 + 0.2 * 0.5 * (parts["D"] + parts["Dq"])
        a, s1, s2 = M.agreement_and_scales(parts, w)
        full[tag] = (a, s1, s2)
    for k in range(3):
        assert full["full"][k].equals(full["trunc"][k])
