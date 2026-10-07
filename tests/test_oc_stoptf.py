"""oc_stoptf tests: stop-timeframe logic on synthetic 1m paths + causality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_stoptf"
sys.path.insert(0, str(OC))
import stoptf as S

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = S.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_size_mult():
    assert S.size_mult(0) == 1.0
    assert abs(S.size_mult(4) - 0.2) < 1e-12


def test_find_fill_strict():
    assert S.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert S.find_fill(np.array([100.0, 99.99]), 100.0) == 1


def test_d0_close5_clock_only():
    # sl dip on a non-clock minute does NOT stop D0; S1 stops there.
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)  # 96.0
    m = 21  # (21+1)%5 != 0 -> not a close5 clock minute
    assert (m + 1) % 5 != 0
    C[m] = sl - 0.01
    O[m + 1] = 95.0
    r0, x0, h0 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close5")
    assert h0 == "time"  # D0 ignores the non-clock dip
    r1, x1, h1 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close1")
    assert h1 == "stop" and x1 == m + 1
    assert abs(r1 - (95.0 / lv - 1 - MK - TK)) < 1e-12


def test_s15_slower_than_d0():
    # dip below sl on a close5 minute that is NOT a close15 minute:
    # D0 stops, S15 holds to timeout.
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    m = 24  # (24+1)%5==0 but (24+1)%15 != 0
    assert (m + 1) % 5 == 0 and (m + 1) % 15 != 0
    C[m] = sl - 0.01
    O[m + 1] = 95.0
    r0, x0, h0 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close5")
    assert h0 == "stop" and x0 == m + 1
    r15, x15, h15 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close15")
    assert h15 == "time" and x15 == 240


def test_s15_fires_on_15m_clock():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    m = 29  # (29+1)%15==0 -> both close5 and close15 clock
    assert (m + 1) % 5 == 0 and (m + 1) % 15 == 0
    C[m] = sl - 0.01
    O[m + 1] = 95.5
    for clock in ("close5", "close15", "close1"):
        r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, clock)
        assert h == "stop" and x == m + 1, clock
        assert abs(r - (95.5 / lv - 1 - MK - TK)) < 1e-12


def test_stop_first_same_minute_all_clocks():
    for clock in ("close5", "close15", "close1"):
        O, H, L, C = _flat()
        lv, sg, f = 100.0, 0.01, 20
        tp = lv * (1 + sg)
        # minute 29 is a clock minute for all three clocks
        H[29] = tp + 0.01
        C[29] = lv * (1 - 4 * sg) - 0.01
        r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, clock)
        assert h == "stop", clock  # stop-first beats same-minute TP


def test_backstop_beats_stop_and_tp():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[29] = tp + 0.01
    C[29] = lv * (1 - 4 * sg) - 0.01
    L[29] = lv * (1 - 8 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close5")
    assert h == "backstop" and x == 29


def test_tp_strict_and_fees():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[30] = tp  # touch == tp is NOT a TP (strict >)
    r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close1")
    assert h == "time"
    H[31] = tp + 1e-9
    r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close1")
    assert h == "tp" and x == 31
    assert abs(r - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_timeout_funding_only_on_settle():
    O, H, L, C = _flat()
    lv, sg, f, o2 = 100.0, 0.01, 20, 101.0
    r0, x0, h0 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, o2, False, "close5")
    r1, x1, h1 = S.outcome_stop_tf(H, L, C, O, f, lv, sg, o2, True, "close15")
    assert (h0, h1) == ("time", "time") and (x0, x1) == (240, 240)
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_stop_at_239_uses_next_bar_open():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    C[239] = sl - 0.01  # 239 is a clock minute for all clocks
    o2 = 94.0
    r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, o2, False, "close5")
    assert h == "stop" and x == 240
    assert abs(r - (o2 / lv - 1 - MK - TK)) < 1e-12


def test_nan_never_triggers():
    O, H, L, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl = lv * (1 - 4 * sg)
    C[29] = np.nan
    L[25] = np.nan
    H[30] = np.nan
    r, x, h = S.outcome_stop_tf(H, L, C, O, f, lv, sg, 99.0, False, "close1")
    assert h == "time"  # NaN closes/lows/highs never trigger


def test_causality_stop_uses_closed_minute_only():
    # n at live minute m uses C at T+m-1 only (fill sizing is causal).
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = S.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
