"""oc_presample2 tests: row knobs on synthetic paths + causality + truncation."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC2 = ROOT / "research/tournament/oc_presample2"
OC1 = ROOT / "research/tournament/oc_presample"
sys.path.insert(0, str(OC2))
sys.path.insert(0, str(OC1))
import presample2 as P2
import presample as P1

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    Cc = np.full(n, o)
    return O, H, Lw, Cc


def test_strict_fill():
    lv = 100.0
    assert P2.find_fill(np.full(223, 100.0), lv) is None  # touch: NO fill
    low = np.full(223, 100.0)
    low[5] = 99.99
    assert P2.find_fill(low, lv) == 5
    assert P2.find_fill(np.full(223, np.nan), lv) is None  # NaN never fills


def test_tp_hit_handchecked():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how, gap = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 99.0, False,
                                      stop="close5", tp_mult=1.0)
    assert how == "tp" and x == 30 and gap is None
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_tp15_level_handchecked():
    # Path rallies +1.2 sg: TP10 fires, TP15 does not (times out instead).
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[30] = lv * (1 + 1.2 * sg)
    r10, x10, h10, _ = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 100.5, False,
                                      stop="close5", tp_mult=1.0)
    r15, x15, h15, _ = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 100.5, False,
                                      stop="close5", tp_mult=1.5)
    assert (h10, x10) == ("tp", 30)
    assert h15 == "time" and x15 == 240
    assert abs(r10 - (lv * 1.01 / lv - 1 - 2 * MK)) < 1e-12
    assert abs(r15 - (100.5 / lv - 1 - MK - TK)) < 1e-12


def test_stop_first_same_minute_close5():
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    H[29] = lv * (1 + sg) + 0.01
    Cc[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how, gap = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 99.0, False,
                                      stop="close5", tp_mult=1.0)
    assert how == "stop"
    assert abs(ret - (O[x] / lv - 1 - MK - TK)) < 1e-12


def test_touch_stop_fires_where_close5_does_not():
    # Whipsaw: intrabar low pierces sl but no 5-minute close <= sl.
    # close5 -> timeout; touch -> stop exit at min(sl, open).
    O, H, Lw, Cc = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    Lw[33] = sl - 0.05  # low pierces; close stays flat (no close5 trigger)
    O[33] = sl + 0.02  # open above sl -> exit px = sl
    rc, xc, hc, _ = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 100.5, False,
                                   stop="close5", tp_mult=1.0)
    rt, xt, ht, gap = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, 100.5, False,
                                     stop="touch", tp_mult=1.0)
    assert hc == "time" and xc == 240
    assert ht == "stop" and xt == 33
    assert abs(rt - (sl / lv - 1 - MK - TK)) < 1e-12
    assert gap is not None and abs(gap) < 1e-9


def test_timeout_funding_handchecked():
    O, H, Lw, Cc = _flat()
    kw = dict(stop="close5", tp_mult=1.0)
    r0, x0, h0, _ = P2.outcome_row(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0,
                                   False, **kw)
    r1, x1, h1, _ = P2.outcome_row(H, Lw, Cc, O, 20, 100.0, 0.01, 101.0,
                                   True, **kw)
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12
    assert abs(r0 - (101.0 / 100.0 - 1 - MK - TK)) < 1e-12


def test_g2_knobs_match_oc_presample_outcome():
    # G2-knob outcome_row == oc_presample outcome_d0 on TP/stop/time paths.
    rng = np.random.default_rng(7)
    O = 100 + rng.standard_normal(240).cumsum() * 0.05 + 100.0
    H = O + np.abs(rng.standard_normal(240)) * 0.1
    Lw = O - np.abs(rng.standard_normal(240)) * 0.1
    Cc = O + rng.standard_normal(240) * 0.02
    for f, sg in ((16, 0.008), (100, 0.015), (200, 0.02)):
        lv = O[f] * 0.97
        a = P1.outcome_d0(H, Lw, Cc, O, f, lv, sg, O[-1] + 0.1, True)
        b = P2.outcome_row(H, Lw, Cc, O, f, lv, sg, O[-1] + 0.1, True,
                           stop="close5", tp_mult=1.0)
        assert a[1:] == b[1:] and abs(a[0] - b[0]) < 1e-12


def test_row_table_budget_scales_with_kd():
    assert abs(P2.ROWS["G2"]["budget"] - 0.26 * 1.7) < 1e-12
    assert abs(P2.ROWS["KD13"]["budget"] - 0.26 * 1.3) < 1e-12
    assert abs(P2.ROWS["KD20"]["budget"] - 0.26 * 2.0) < 1e-12
    # KD13 budget rejects a rung G2 accepts (same w, sg).
    w, sg = 0.05, 0.01  # add-on risk = 0.05*(4*0.01+0.02) = 0.003
    assert P2.budget_ok_amt(0.336, w, sg, P2.ROWS["G2"]["budget"])  # 0.339<=0.442
    assert not P2.budget_ok_amt(0.336, w, sg, P2.ROWS["KD13"]["budget"])  # 0.339>0.338
    # NOCAP keeps full weight where G2 clips.
    assert abs(P2.cap_apply(1.95, 0.1, 2.0) - 0.05) < 1e-9
    assert P2.cap_apply(1.95, 0.1, None) == 0.1
    # NOB1 mult is 1.0 (no division by 1+n).
    assert P2.ROWS["NOB1"]["corr"] is False
    assert P2.U * P2.ROWS["NOB1"]["kd"] == P2.U * 1.7


def test_sigma_excludes_current_bar():
    opens = np.linspace(100, 200, 400)
    sg = P2.compute_sigma(opens)
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
    assert (P2.n_vector(co, oo, ss) == 0).all()
    co[0, :] = 100.0 * (1 - 2.5 * 0.01)
    assert (P2.n_vector(co, oo, ss) == 1).all()  # at-threshold counts
    co[1, 3] = np.nan
    n = P2.n_vector(co, oo, ss)
    assert n[3] == 1 and n[0] == 1
    oo2 = oo.copy()
    oo2[0] = np.nan
    assert (P2.n_vector(co, oo2, ss) == 0).all()


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
    grids = P2.build_grids(idx, ["BTCUSDT"], D)
    bts, ob, sg = grids[0]
    S = bts[0]
    E = bts[1]  # interval covers exactly the first bar
    js = [j for j, T in enumerate(bts) if S <= T < E]
    assert len(js) == 1
    jj = {j: bts[j] for j in js}
    cell, led = P2.simulate_interval(idx, D, ["BTCUSDT"], jj, ob, sg, S, E,
                                    row="G2", label="trunc")
    assert cell is not None
    assert all(r[2] == str(S) for r in led)  # all fills on the first bar
    js2 = [j for j, T in enumerate(bts) if S <= T < E + pd.Timedelta(hours=4)]
    assert len(js2) >= 2  # grid really has a second bar
