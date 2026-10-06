"""oc_crash2020 tests: core logic on synthetic 1m paths + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_crash2020"
sys.path.insert(0, str(OC))
import crash as C

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    Cc = np.full(n, o)
    return O, H, Lw, Cc


def test_strict_fill():
    lv = 100.0
    assert C.find_fill(np.full(223, 100.0), lv) is None  # touch == level: NO fill
    low = np.full(223, 100.0)
    low[5] = 99.99
    assert C.find_fill(low, lv) == 5
    low2 = np.full(223, np.nan)
    low2[5] = 99.0
    assert C.find_fill(low2, lv) == 5  # NaN never fills, finite does
    assert C.find_fill(np.full(223, np.nan), lv) is None


def test_tp_hit():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how, gap = C.outcome_d0(H, Lw, Cc, O, f, lv, sg, 99.0, False)
    assert how == "tp" and x == 30 and gap is None
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_stop_first_same_minute():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[29] = lv * (1 + sg) + 0.01
    Cc[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how, gap = C.outcome_d0(H, Lw, Cc, O, f, lv, sg, 99.0, False)
    assert how == "stop"
    assert abs(ret - (O[x] / lv - 1 - MK - TK)) < 1e-12
    assert gap is not None and gap <= 0  # next-open fill at/above the stop


def test_backstop_gap_pays_open_and_flags():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    bl = lv * (1 - 8 * sg)
    Lw[25] = bl - 5.0
    O[25] = bl - 5.0  # gapped through: open worse than the level
    ret, x, how, gap = C.outcome_d0(H, Lw, Cc, O, f, lv, sg, 99.0, False)
    assert how == "backstop" and x == 25
    assert abs(ret - (O[25] / lv - 1 - MK - TK)) < 1e-12
    assert gap > 1.0  # worse than the level by > 1 sigma -> gap-through


def test_timeout_funding():
    O, H, Lw, Cc = _flat()
    r0, x0, h0, _ = C.outcome_d0(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0, False)
    r1, x1, h1, _ = C.outcome_d0(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0, True)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_budget_and_cap():
    assert C.budget_ok(0.0, 0.05, 0.01)  # 0.05*(0.04+0.02)=0.003 <= 0.442
    assert not C.budget_ok(0.44, 0.05, 0.01)
    assert C.cap_apply(1.5, 0.1, 2.0) == 0.1
    assert abs(C.cap_apply(1.95, 0.1, 2.0) - 0.05) < 1e-9  # cut to the room
    assert C.cap_apply(2.0, 0.1, 2.0) == 0.0  # no room -> skip
    assert C.cap_apply(5.0, 0.1, None) == 0.1  # NOCAP untouched


def test_sigma_excludes_current_bar():
    opens = np.linspace(100, 200, 400)
    sg = C.compute_sigma(opens)
    assert np.isnan(sg[:120]).all()  # warm-up: min_periods 120
    assert np.isfinite(sg[130])
    # last value must equal std of returns ending at index -2 (shift 1)
    r = pd.Series(opens).pct_change().to_numpy()
    expect = np.std(r[39:399], ddof=1)  # 360 bars ending at j-1 = 399
    assert abs(sg[399] - expect) < 1e-12


def test_n_vector_causal_and_nan_safe():
    W = 8
    co = np.full((4, W), 100.0)
    oo = np.full(4, 100.0)
    ss = np.full(4, 0.01)
    assert (C.n_vector(co, oo, ss) == 0).all()  # flat: nobody flushing
    co[0, :] = 100.0 * (1 - 2.5 * 0.01)  # exactly at the threshold counts
    assert (C.n_vector(co, oo, ss) == 1).all()
    co[1, 3] = np.nan  # NaN close never counts
    n = C.n_vector(co, oo, ss)
    assert n[3] == 1 and n[0] == 1
    oo2 = oo.copy()
    oo2[0] = np.nan  # NaN open/sigma -> that coin never counts
    assert (C.n_vector(co, oo2, ss) == 0).all()


def test_sizing_formula_matches_plan():
    n = 3
    w = C.U * C.KD / (1 + n)
    assert abs(w - (0.25 * 1.75 / 4 / 1.657) * 1.7 / 4) < 1e-12


def test_real_data_march2020_bars_exist():
    """Smoke: real 1m loads and March-2020 sigma is finite for BTC (warm-up done)."""
    idx, d = C.load_1m("BTCUSDT")
    assert idx[0] <= pd.Timestamp("2020-01-01", tz="UTC")
    bts = pd.date_range(C.ORIGIN, pd.Timestamp("2020-04-01", tz="UTC"), freq="4h")
    offs = ((bts - idx[0]).total_seconds() // 60).astype(int)
    oo = d["open"][offs].astype(float)
    sg = C.compute_sigma(oo)
    j = int(np.searchsorted(bts, pd.Timestamp("2020-03-12", tz="UTC"))) - 1
    assert np.isfinite(oo[j]) and np.isfinite(sg[j]) and sg[j] > 0
