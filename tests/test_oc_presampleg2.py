"""oc_presampleg2 tests (PLAN.md): frozen dip primitives + the new book leg.

Light synthetic cases only (no heavy data, no fitting). Run:
  .venv/Scripts/python.exe -m pytest tests/test_oc_presampleg2.py -q
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

g2 = importlib.util.spec_from_file_location(
    "g2mod", ROOT / "research/tournament/oc_presampleg2/presampleg2.py")
G = importlib.util.module_from_spec(g2)
g2.loader.exec_module(G)
p2 = G.p2


# ---------------- frozen dip primitives (imported, behaviour pinned) ----------------
def test_strict_fill():
    assert p2.find_fill(np.array([10.0, 9.0, 9.0]), 9.0) is None  # touch is NOT a fill
    assert p2.find_fill(np.array([10.0, 8.9, 9.0]), 9.0) == 1      # strict trade-through


def test_stop_first_same_minute():
    n = 240
    O = np.full(n, 100.0)
    H = np.full(n, 100.0)
    L = np.full(n, 100.0)
    C = np.full(n, 100.0)
    L[50] = 50.0   # below backstop AND stop
    H[50] = 500.0  # above TP in the same minute
    ret, x, how, _ = p2.outcome_row(H, L, C, O, 10, 100.0, 0.01, 100.0, False)
    assert how in ("stop", "backstop") and x == 50


def test_funding_only_on_settle_timeout():
    n = 240
    O = H = L = C = np.full(n, 100.0)
    r_set, _, how_s, _ = p2.outcome_row(H, L, C, O, 10, 100.0, 0.01, 100.0, True)
    r_nos, _, how_n, _ = p2.outcome_row(H, L, C, O, 10, 100.0, 0.01, 100.0, False)
    assert how_s == how_n == "time"
    assert r_set == r_nos - p2.FUND


def test_budget_and_cap():
    assert not p2.budget_ok_amt(0.0, 10.0, 0.01, 0.26 * 1.7)  # way over budget
    assert p2.budget_ok_amt(0.0, 1e-6, 0.01, 0.26 * 1.7)
    assert p2.cap_apply(1.9, 0.5, 2.0) == abs(2.0 - 1.9)  # cut to room (fp-exact)
    assert p2.cap_apply(2.0, 0.5, 2.0) == 0.0                # no room -> skip
    assert p2.cap_apply(5.0, 0.5, None) == 0.5               # no cap


# ---------------- book leg ----------------
def test_book_levels():
    sl, tp = G.book_levels(100.0, 1.0, 0.01)
    assert (sl, tp) == (97.0, 106.0)
    sl, tp = G.book_levels(100.0, -1.0, 0.01)
    assert (sl, tp) == (103.0, 94.0)


def _mini(mutate=None, opens=None, tgt=0.5):
    """One-bar synthetic world. Returns (cell, dled, bled)."""
    T = pd.Timestamp("2019-06-01 04:00", tz="UTC")
    idx0 = T - pd.Timedelta(hours=4)
    idx = pd.date_range(idx0, periods=600, freq="1min")
    off = 240
    n = len(idx)
    o = np.full(n, 100.0)
    h = np.full(n, 100.0)
    l = np.full(n, 100.0)
    c = np.full(n, 100.0)
    if mutate:
        mutate(o, h, l, c, off)
    D = {"BTCUSDT": {"open": o, "high": h, "low": l, "close": c}}
    bars = {0: T}
    ob = {"BTCUSDT": np.array([100.0])} if opens is None else {"BTCUSDT": opens}
    sg = {"BTCUSDT": np.array([np.nan])} if opens is None else {
        "BTCUSDT": np.array([np.nan] * (len(opens) - 1) + [0.01])}
    S, E = T - pd.Timedelta(hours=1), T + pd.Timedelta(hours=5)
    bw = {"BTCUSDT": np.array([tgt])}
    return G.simulate_interval_g2(idx, D, ["BTCUSDT"], bars, ob, sg, S, E,
                                  books_w=bw, sleeve=False, label="t"), T


def test_book_limit_fill_and_pnl():
    def dip(o, h, l, c, off):
        l[off + 10] = 99.5  # below the 99.9 buy limit -> fill at minute 10
    (cell, _, bled), _ = _mini(dip)
    assert cell["book_fills"] == 1
    assert bled[0][3] == "buy" and bled[0][5] == 10
    # hand check: 0.5*(100/99.9-1) - maker*0.5 - funding*0.5
    # (T+4h = 08:00 UTC is a funding settlement; longs pay 0.0001)
    expect = 0.5 * (100.0 / 99.9 - 1) - G.MAKER * 0.5 - G.FUND * 0.5
    assert abs(cell["book_pnl"] - round(expect, 6)) < 2e-9
    assert abs(cell["end_equity"] - round(1 + expect, 6)) < 2e-9


def test_book_expiry_no_fill():
    (cell, _, bled), _ = _mini()  # flat 100s: low never < 99.9
    assert cell["book_fills"] == 0
    assert bled[0][3] == "exp"
    assert cell["book_pnl"] == 0.0 and cell["end_equity"] == 1.0


def test_book_no_fill_first_5_min():
    def early(o, h, l, c, off):
        l[off + 2] = 99.5  # inside the forbidden first-5-min window
    (cell, _, _), _ = _mini(early)
    assert cell["book_fills"] == 0  # expired, not filled


def test_book_stop_first():
    opens = np.tile([100.0, 101.0], 200)  # finite sigma_d

    def crash(o, h, l, c, off):
        l[off + 10] = 99.5
        l[off + 20] = 0.01   # below any SL
        h[off + 20] = 1e6    # above any TP, same minute -> stop first
    T = pd.Timestamp("2019-06-01 04:00", tz="UTC")
    idx0 = T - pd.Timedelta(hours=4)
    idx = pd.date_range(idx0, periods=600, freq="1min")
    off = 240
    n = len(idx)
    o = np.full(n, 100.0)
    h = np.full(n, 100.0)
    l = np.full(n, 100.0)
    c = np.full(n, 100.0)
    crash(o, h, l, c, off)
    D = {"BTCUSDT": {"open": o, "high": h, "low": l, "close": c}}
    S, E = T - pd.Timedelta(hours=1), T + pd.Timedelta(hours=5)
    (cell, _, bled) = G.simulate_interval_g2(
        idx, D, ["BTCUSDT"], {399: T}, {"BTCUSDT": opens},
        {"BTCUSDT": np.full(400, np.nan)}, S, E,
        books_w={"BTCUSDT": np.array([0.5])}, sleeve=False, label="t")
    hows = [r[3] for r in bled]
    assert "buy" in hows and "stop" in hows
    assert cell["book_stops"] == 1 and cell["book_tps"] == 0


def test_causal_book_lag():
    t0 = pd.Timestamp("2019-06-01 00:00", tz="UTC")
    pb = pd.DataFrame({"BTCUSDT": [0.3, 0.7]},
                      index=pd.DatetimeIndex([t0, t0 + pd.Timedelta(hours=4)]))
    bts = pd.DatetimeIndex([t0 + pd.Timedelta(hours=4),   # sees row t0 only
                            t0 + pd.Timedelta(hours=8)])  # sees row t0+4h
    got = G.book_targets_for_phase(pb, bts)["BTCUSDT"]
    assert list(got) == [0.3, 0.7]
    early = pd.DatetimeIndex([t0 - pd.Timedelta(hours=1)])
    assert G.book_targets_for_phase(pb, early)["BTCUSDT"][0] == 0.0


def test_sigma_causality():
    base = np.full(400, 100.0)
    spiked = base.copy()
    spiked[300] = 150.0  # spike AT bar 300
    s0 = G.book_sig_d({"BTCUSDT": base})["BTCUSDT"]
    s1 = G.book_sig_d({"BTCUSDT": spiked})["BTCUSDT"]
    assert s0[300] == s1[300]      # sigma at j excludes bar j
    assert s1[301] != s0[301]      # but the spike enters later sigmas


def test_truncation_outside_window():
    T = pd.Timestamp("2019-06-01 04:00", tz="UTC")
    idx = pd.date_range(T - pd.Timedelta(hours=4), periods=600, freq="1min")
    o = np.full(600, 100.0)
    D = {"BTCUSDT": {"open": o, "high": o.copy(), "low": o.copy(), "close": o.copy()}}
    S, E = T + pd.Timedelta(hours=1), T + pd.Timedelta(hours=5)  # bar NOT in window
    out = G.simulate_interval_g2(idx, D, ["BTCUSDT"], {0: T},
                                 {"BTCUSDT": np.array([100.0])},
                                 {"BTCUSDT": np.array([np.nan])}, S, E,
                                 books_w=None, sleeve=True, label="t")
    assert out[0] is None  # no bar traded -> no cell
