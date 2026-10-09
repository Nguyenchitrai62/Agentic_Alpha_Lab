"""oc_presample tests: vendored core on synthetic paths + causality + truncation."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_presample"
sys.path.insert(0, str(OC))
import presample as P

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    Cc = np.full(n, o)
    return O, H, Lw, Cc


def test_strict_fill():
    lv = 100.0
    assert P.find_fill(np.full(223, 100.0), lv) is None  # touch: NO fill
    low = np.full(223, 100.0)
    low[5] = 99.99
    assert P.find_fill(low, lv) == 5
    assert P.find_fill(np.full(223, np.nan), lv) is None  # NaN never fills


def test_tp_hit_handchecked():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how, gap = P.outcome_d0(H, Lw, Cc, O, f, lv, sg, 99.0, False)
    assert how == "tp" and x == 30 and gap is None
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_stop_first_same_minute():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[29] = lv * (1 + sg) + 0.01
    Cc[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how, gap = P.outcome_d0(H, Lw, Cc, O, f, lv, sg, 99.0, False)
    assert how == "stop"
    assert abs(ret - (O[x] / lv - 1 - MK - TK)) < 1e-12


def test_timeout_funding_handchecked():
    O, H, Lw, Cc = _flat()
    r0, x0, h0, _ = P.outcome_d0(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0, False)
    r1, x1, h1, _ = P.outcome_d0(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0, True)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12
    assert abs(r0 - (101.0 / 100.0 - 1 - MK - TK)) < 1e-12


def test_budget_and_cap_handchecked():
    assert P.budget_ok(0.0, 0.05, 0.01)
    assert not P.budget_ok(0.44, 0.05, 0.01)
    assert P.cap_apply(1.5, 0.1, 2.0) == 0.1
    assert abs(P.cap_apply(1.95, 0.1, 2.0) - 0.05) < 1e-9
    assert P.cap_apply(2.0, 0.1, 2.0) == 0.0
    assert P.U * P.KD / 4 == (0.25 * 1.75 / 4 / 1.657) * 1.7 / 4


def test_sigma_excludes_current_bar():
    opens = np.linspace(100, 200, 400)
    sg = P.compute_sigma(opens)
    assert np.isnan(sg[:120]).all()  # warm-up: min_periods 120
    assert np.isfinite(sg[130])
    r = pd.Series(opens).pct_change().to_numpy()
    expect = np.std(r[39:399], ddof=1)  # 360 bars ending at j-1 = 399
    assert abs(sg[399] - expect) < 1e-12


def test_n_vector_causal_and_nan_safe():
    W = 8
    co = np.full((4, W), 100.0)
    oo = np.full(4, 100.0)
    ss = np.full(4, 0.01)
    assert (P.n_vector(co, oo, ss) == 0).all()
    co[0, :] = 100.0 * (1 - 2.5 * 0.01)
    assert (P.n_vector(co, oo, ss) == 1).all()  # at-threshold counts
    co[1, 3] = np.nan
    n = P.n_vector(co, oo, ss)
    assert n[3] == 1 and n[0] == 1
    oo2 = oo.copy()
    oo2[0] = np.nan
    assert (P.n_vector(co, oo2, ss) == 0).all()


def test_interval_truncation_no_bars_after_end():
    """simulate_interval opens rungs only on bars with open in [S, E)."""
    idx = pd.date_range(pd.Timestamp("2020-01-01", tz="UTC"),
                        pd.Timestamp("2020-01-02", tz="UTC"), freq="1min")
    n = len(idx)
    D = {"BTCUSDT": {"open": np.full(n, 100.0, dtype=np.float32),
                     "high": np.full(n, 100.0, dtype=np.float32),
                     "low": np.full(n, 100.0, dtype=np.float32),
                     "close": np.full(n, 100.0, dtype=np.float32)}}
    D["BTCUSDT"]["low"][16:239] = 90.0  # would fill any rung in reach
    grids = P.build_grids(idx, ["BTCUSDT"], D)
    bts, ob, sg = grids[0]
    S = bts[0]
    E = bts[1]  # interval covers exactly the first bar
    js = [j for j, T in enumerate(bts) if S <= T < E]
    assert len(js) == 1
    jj = {j: bts[j] for j in js}
    cell, led = P.simulate_interval(idx, D, ["BTCUSDT"], jj, ob, sg, S, E,
                                    label="trunc")
    assert cell is not None
    assert all(r[2] == str(S) for r in led)  # all fills on the first bar
    # a bar AT E must not be simulated even if present in the grid
    js2 = [j for j, T in enumerate(bts) if S <= T < E + pd.Timedelta(hours=4)]
    assert len(js2) >= 2  # grid really has a second bar


def test_marks_hold_through_nan_gaps():
    """Outage NaNs hold the last mark: min/DD stay finite (REPORT fix)."""
    idx = pd.date_range(pd.Timestamp("2020-01-01", tz="UTC"),
                        pd.Timestamp("2020-01-02", tz="UTC"), freq="1min")
    n = len(idx)
    o = np.full(n, 100.0, dtype=np.float32)
    c = np.full(n, 100.0, dtype=np.float32)
    c[30:60] = np.nan  # outage gap with no prints
    low = np.full(n, 100.0, dtype=np.float32)
    low[16] = 90.0  # one fill on the first bar
    D = {"BTCUSDT": {"open": o, "high": o.copy(), "low": low, "close": c},
         "ETHUSDT": {"open": o.copy(), "high": o.copy(),
                     "low": o.copy(), "close": o.copy()}}
    S = idx[0]
    E = idx[0] + pd.Timedelta(hours=4)
    jj = {0: S}
    ob = {"BTCUSDT": np.array([100.0]),  # hand-set finite sigma
          "ETHUSDT": np.array([100.0])}  # (flat opens would give sigma 0)
    sg = {"BTCUSDT": np.array([0.01]),
          "ETHUSDT": np.array([0.01])}
    cell, led = P.simulate_interval(idx, D, ["BTCUSDT", "ETHUSDT"], jj, ob,
                                    sg, S, E, label="nanmark")
    assert cell is not None and len(led) >= 1
    assert np.isfinite(cell["min_marked"]) and np.isfinite(cell["max_dd_pct"])


def test_spot_store_covers_only_presample_window():
    """Pack-level truncation: no presample parquet extends past 2020-09."""
    import json
    man = json.loads((ROOT / "data/raw/spot_1m_presample_20261007"
                      / "manifest.json").read_text())
    for sym, v in man["symbols"].items():
        assert v["months"][-1] == "2020-09", sym
        assert v["last_bar"] <= "2020-10-01", sym
        assert v["first_bar"] >= "2017-08-01", sym
