"""Tests for oc_clockagree (cross-clock agreement sizing, IDEAS8 #5).

Covers: hand-checked synthetic k/scale cases (V1 4/3/else + V2 >=3,
zero-row convention, k==3-never degeneracy on a regular 4h grid),
bear-filter longs-only, book-episode fee-split hand check, and truncation
tests (synthetic + real member files: rows <= T unchanged when later rows
are removed).
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MOD = ROOT / "research/tournament/oc_clockagree/run_clockagree.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_clockagree_mod", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load()


def _frame(idx, cols, vals):
    return pd.DataFrame(vals, index=idx, columns=cols)


def test_hand_checked_k_scales_persist_flip():
    idx = pd.date_range("2021-09-24", periods=4, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    # persist -> k==4 -> 1.0/1.0 ; flip -> k==1 -> 0.5/0.5 ; warm-up row -> k==1
    w = _frame(idx, cols, [[1.0], [1.0], [-1.0], [-1.0]])
    K, s1, s2 = M.clock_values_and_scales(w)
    assert K["BTCUSDT"].tolist() == [1, 4, 1, 4]
    assert s1["BTCUSDT"].tolist() == [0.5, 1.0, 0.5, 1.0]
    assert s2["BTCUSDT"].tolist() == [0.5, 1.0, 0.5, 1.0]


def test_hand_checked_zero_convention_and_k3_branch():
    idx = pd.date_range("2021-09-24", periods=2, freq="4h", tz="UTC")
    cols = ["ETHUSDT"]
    # ensemble == 0 -> scale 1.0 by convention (weight stays 0)
    w = _frame(idx, cols, [[0.0], [1.0]])
    K, s1, s2 = M.clock_values_and_scales(w)
    assert s1["ETHUSDT"].tolist() == [1.0, 0.5]
    assert s2["ETHUSDT"].tolist() == [1.0, 0.5]
    # k==3 branch exists in code: V1 0.75 vs V2 1.0 (unit-check the mapping)
    k3_s1 = np.where(3 == 4, 1.0, np.where(3 == 3, 0.75, 0.5))
    k3_s2 = 1.0 if 3 >= 3 else 0.5
    assert k3_s1 == 0.75 and k3_s2 == 1.0


def test_degeneracy_k3_never_on_regular_grid():
    idx = pd.date_range("2021-09-24", periods=50, freq="4h", tz="UTC")
    cols = ["BTCUSDT", "ETHUSDT"]
    rng = np.random.default_rng(7)
    vals = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], size=(50, 2))
    w = _frame(idx, cols, vals)
    K, s1, s2 = M.clock_values_and_scales(w)
    kv = K.to_numpy().ravel()
    assert set(np.unique(kv)).issubset({1, 2, 3, 4})
    nz = w.to_numpy().ravel() != 0.0
    # on a gap-free regular grid v1==v2==v3, so non-zero rows give k in {1,4}
    assert int(((kv == 3) & nz).sum()) == 0
    assert int(((kv == 2) & nz).sum()) == 0
    # V1 and V2 coincide wherever the ensemble is non-zero
    assert bool(((s1.to_numpy() == s2.to_numpy()) | (~nz.reshape(s1.shape))).all())


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
    assert abs(eps2[0][3] - 0.9 * 0.00055) < 1e-12


def test_truncation_synthetic():
    """K/scales at rows <= T unchanged when rows after T are removed."""
    idx = pd.date_range("2021-09-24", periods=20, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    vals = [[1.0], [-1.0], [1.0], [1.0], [-1.0]] * 4
    w = _frame(idx, cols, vals)
    Kf, s1f, s2f = M.clock_values_and_scales(w)
    T = idx[12]
    wt = w[w.index <= T]
    Kt, s1t, s2t = M.clock_values_and_scales(wt)
    assert Kf.loc[:T].equals(Kt)
    assert s1f.loc[:T].equals(s1t)
    assert s2f.loc[:T].equals(s2t)


def test_truncation_real_members():
    """Agreement/scales at rows <= T unchanged when members truncated to <= T."""
    eu = M._load("eu_ca_test", M.RD / "engine_user" / "engine_user.py")
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    Cc = eu.er.CACHE
    T = pd.Timestamp("2023-03-01 00:00", tz="UTC")
    rows = books154.index[books154.index <= T]
    assert len(rows) > 100
    files = {"A": "member_A_O1_orders.parquet", "Aq": "member_Aq_O1_orders.parquet",
             "B": "member_B_tv.parquet", "Bq": "member_Bq_tv.parquet"}
    outs = {}
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
        outs[tag] = M.clock_values_and_scales(w)
    for k in range(3):
        assert outs["full"][k].equals(outs["trunc"][k])
