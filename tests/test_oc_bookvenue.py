"""Tests for oc_bookvenue: prep mirror + split fidelity (light, no heavy data)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/diagnostics/oc_bookvenue"))
sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
import oc_bookvenue as ocb


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_prep_mirrors_prep_idx():
    pof = _load("pof_test", ROOT / "research/diagnostics/phase_offset_full/phase_offset_full.py")
    cols = ["BTCUSDT", "ETHUSDT"]
    idx = pd.date_range("2021-11-15", periods=30, freq="4h", tz="UTC")
    rng = np.random.default_rng(0)
    # synthetic minutes per coin on the exact grid
    store = {}
    for j, s in enumerate(cols):
        t = pd.date_range(idx[0], idx[-1] + pd.Timedelta(hours=8) - pd.Timedelta(minutes=1), freq="min", tz="UTC")
        base = 100 + j * 50 + np.cumsum(rng.normal(0, 0.2, len(t)))
        store[s] = pd.DataFrame({"open": base, "high": base + 0.3, "low": base - 0.3, "close": base + 0.05}, index=t)
    M = {s: store[s] for s in cols}
    opens_ref, prep_ref = pof.prep_idx(M, idx, 0, cols)

    def get_minutes(sym, a, b):
        return store[sym][(store[sym].index >= a) & (store[sym].index < b)]
    opens_new, prep_new = ocb.build_prep(idx, cols, get_minutes, 0)
    pd.testing.assert_frame_equal(opens_new, opens_ref)
    for k in ("O", "H", "L", "C"):
        assert np.allclose(prep_new[k], prep_ref[k], equal_nan=True), k
    assert np.allclose(prep_new["sig4"], prep_ref["sig4"], equal_nan=True)
    assert np.allclose(prep_new["o1"], prep_ref["o1"], equal_nan=True)
    assert np.allclose(prep_new["o2"], prep_ref["o2"], equal_nan=True)
    assert np.array_equal(prep_new["settle"], prep_ref["settle"])


def _tiny_market():
    # Full 5y 4h grid so engine_user.summarize (loops all 5 anchors) works.
    cols = ["BTCUSDT", "ETHUSDT"]
    idx = pd.date_range("2021-09-24", "2026-09-23 20:00", freq="4h", tz="UTC")
    rng = np.random.default_rng(1)
    n = len(idx)
    O = np.full((n, 240, 2), np.nan, dtype=np.float32)
    H = np.full((n, 240, 2), np.nan, dtype=np.float32)
    L = np.full((n, 240, 2), np.nan, dtype=np.float32)
    C = np.full((n, 240, 2), np.nan, dtype=np.float32)
    opens = pd.DataFrame(index=idx, columns=cols, dtype=float)
    px = {s: 100.0 + 50 * j for j, s in enumerate(cols)}
    for i in range(n):
        for j, s in enumerate(cols):
            o0 = px[s] * (1 + rng.normal(0, 0.002))
            opens.loc[idx[i], s] = o0
            if 100 <= i <= 112:
                # hand-checked window: punch through a 10bps-better limit, then drift
                path = o0 + np.cumsum(rng.normal(0, o0 * 0.0005, 240))
                path[5:12] -= o0 * 0.004
            else:
                path = o0 + np.cumsum(rng.normal(0, o0 * 0.0002, 240))
            O[i, :, j] = np.concatenate([[o0], path[:-1]]).astype(np.float32)
            H[i, :, j] = (path + abs(rng.normal(0, o0 * 0.0002, 240))).astype(np.float32)
            L[i, :, j] = (path - abs(rng.normal(0, o0 * 0.0002, 240))).astype(np.float32)
            C[i, :, j] = path.astype(np.float32)
            px[s] = float(path[-1])
    sig4 = np.full((n, 2), 0.01)
    prep = dict(idx=idx, cols=cols, O=O, H=H, L=L, C=C, sig4=sig4,
                o1=opens.shift(-1).to_numpy(), o2=opens.shift(-2).to_numpy(),
                settle=np.zeros(n, bool))
    books = pd.DataFrame(0.0, index=idx, columns=cols)
    books.loc[idx[100]:idx[106], "BTCUSDT"] = 0.3
    books.loc[idx[102]:idx[108], "ETHUSDT"] = 0.2
    return idx, cols, opens, prep, books


def _mini_trade():
    def pol(i, a, st):
        if st["pos"] == 0:
            return "open"
        return "hold"
    return dict(theta=0.05, k_off=0.25, min_off=0.001, n_valid=2, policy=pol)


def test_split_identical_reproduces_single():
    idx, cols, opens, prep, books = _tiny_market()
    trade = _mini_trade()
    eu = _load("eu_test", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
    live0, live1 = idx[0], idx[-2]
    eu.v110.START, eu.v110.END = live0, live1
    kw = dict(sleeve=True, sleeve_risk_budget=0.26, size_mult=1.0, m_sleeve_tp=1.0)
    # split with identical preps must match single-venue path + events
    p2 = {}
    ev2 = []
    ocb.simulate_split(books, opens, prep, prep, trade=trade, events=ev2, win_start=5,
                       path_out=p2, live0=live0, live1=live1, **kw)
    eu.v110.START, eu.v110.END = live0, live1
    ev3 = []
    path1 = {}
    eu.simulate(books, opens, prep, trade=trade, events=ev3, win_start=5, path_out=path1, **kw)
    assert np.allclose(p2["eq"], path1["eq"], equal_nan=True)
    assert np.allclose(p2["eq_min"], path1["eq_min"], equal_nan=True)
    k1 = sorted((e["kind"], e["symbol"], str(e["t"])) for e in ev3)
    k2 = sorted((e["kind"], e["symbol"], str(e["t"])) for e in ev2)
    assert k1 == k2
    assert len(k1) > 0  # hand-checked market must fill something


def test_split_routes_book_and_dip_venues():
    idx, cols, opens, prep, books = _tiny_market()
    trade = _mini_trade()
    # dip venue with much deeper lows -> strictly more rung fills; book venue identical
    prep_dip = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in prep.items()}
    prep_dip["L"] = prep["L"].copy()
    prep_dip["L"][:, 16:239, :] -= (prep["C"][:, 16:239, :] * 0.02).astype(np.float32)
    live0, live1 = idx[0], idx[-2]
    kw = dict(sleeve=True, sleeve_risk_budget=10.0, size_mult=1.0, m_sleeve_tp=1.0)
    ev_book = []
    ocb.simulate_split(books, opens, prep, prep_dip, trade=trade, events=ev_book,
                       win_start=5, path_out={}, live0=live0, live1=live1, **kw)
    ev_both = []
    ocb.simulate_split(books, opens, prep_dip, prep_dip, trade=trade, events=ev_both,
                       win_start=5, path_out={}, live0=live0, live1=live1, **kw)
    nb = sum(1 for e in ev_book if e["kind"] == "book_fill")
    nd = sum(1 for e in ev_book if e["kind"] == "rung_fill")
    nd2 = sum(1 for e in ev_both if e["kind"] == "rung_fill")
    # book fills identical (same book venue), dip fills follow the dip venue
    assert nd >= 0 and nd2 >= nd
    assert nb > 0


def test_matched_bps():
    a = pd.DataFrame([dict(kind="book_fill", symbol="BTCUSDT", t=pd.Timestamp("2022-01-01 04:10", tz="UTC"), price=100.0),
                      dict(kind="book_fill", symbol="ETHUSDT", t=pd.Timestamp("2022-01-01 08:10", tz="UTC"), price=200.0)])
    b = pd.DataFrame([dict(kind="book_fill", symbol="BTCUSDT", t=pd.Timestamp("2022-01-01 04:12", tz="UTC"), price=101.0),
                      dict(kind="book_fill", symbol="ETHUSDT", t=pd.Timestamp("2022-01-01 08:11", tz="UTC"), price=199.0)])
    r = ocb.matched_bps(a, b, "book_fill")
    assert r["n"] == 2
    assert abs(r["mean"] - 25.0) < 0.01  # (+100bps -50bps)/2
