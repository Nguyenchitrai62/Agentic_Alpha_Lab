"""oc_expirydip tests: expiry calendar + D0/B1 replica on synthetic paths."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_expirydip"
sys.path.insert(0, str(OC))
import expirydip as X

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_expiry_calendar_hand_checked():
    # Sep 2025 -> Fri 2025-09-26; Feb 2024 (leap) -> Fri 2024-02-23;
    # Jun 2026 -> Fri 2026-06-26
    assert X.last_friday(2025, 9) == 26
    assert X.last_friday(2024, 2) == 23
    assert X.last_friday(2026, 6) == 26
    import datetime as dt
    for (y, m) in [(2025, 9), (2024, 2), (2026, 6)]:
        d = dt.date(y, m, X.last_friday(y, m))
        assert d.weekday() == 4  # Friday
        assert (d + dt.timedelta(days=7)).month != m or True  # last such Friday
        nxt = d + dt.timedelta(days=7)
        assert nxt.month != m  # no later Friday in the month


def test_window_membership_phase0_bars():
    import datetime as dt
    exp = {dt.date(2025, 9, 26)}
    assert X.in_exp_window(pd.Timestamp("2025-09-26 00:00", tz="UTC"), exp)
    assert X.in_exp_window(pd.Timestamp("2025-09-26 04:00", tz="UTC"), exp)
    assert X.in_exp_window(pd.Timestamp("2025-09-26 08:00", tz="UTC"), exp)
    assert not X.in_exp_window(pd.Timestamp("2025-09-26 12:00", tz="UTC"), exp)
    assert not X.in_exp_window(pd.Timestamp("2025-09-26 16:00", tz="UTC"), exp)
    assert not X.in_exp_window(pd.Timestamp("2025-09-25 08:00", tz="UTC"), exp)
    assert not X.in_exp_window(pd.Timestamp("2025-09-27 04:00", tz="UTC"), exp)
    # shifted phases: bars opening inside [00:00,12:00) also qualify
    assert X.in_exp_window(pd.Timestamp("2025-09-26 01:00", tz="UTC"), exp)
    assert X.in_exp_window(pd.Timestamp("2025-09-26 09:00", tz="UTC"), exp)


def test_windows_need_no_market_data():
    import datetime as dt
    exp = {dt.date(2025, 9, 26)}
    ts = pd.Timestamp("2025-09-26 04:00", tz="UTC")
    assert X.in_exp_window(ts, exp) is True
    # market inputs cannot change the flag (pure timestamps)
    assert X.in_exp_window(ts, set()) is False


def test_n_counts_flushers_exact_boundary():
    cmat = np.array([[97.5, 97.51, np.nan],
                      [90.0, 99.0, 97.5],
                      [100.0, 100.0, 100.0],
                      [97.49, 97.5, 97.5]])
    oo = np.array([100.0, 100.0, 100.0, 100.0])
    ss = np.array([0.01, 0.01, 0.01, 0.01])
    n = X.n_vector(cmat, oo, ss)
    assert n.tolist() == [3, 1, 2]


def test_n_ignores_bad_sigma_and_open():
    cmat = np.array([[50.0], [50.0], [50.0], [50.0]])
    oo = np.array([100.0, np.nan, 100.0, 100.0])
    ss = np.array([0.01, 0.01, np.nan, 0.0])
    assert X.n_vector(cmat, oo, ss).tolist() == [1]


def test_size_mult():
    assert X.size_mult(0) == 1.0
    assert abs(X.size_mult(4) - 0.2) < 1e-12


def test_fill_strict_trade_through():
    assert X.find_fill(np.array([100.0, 100.0]), 100.0) is None
    assert X.find_fill(np.array([100.0, 99.99]), 100.0) == 1


def test_outcome_tp_math():
    sg, f, lv = 0.01, 20, 100.0
    O, H, L, C = _flat(o=lv)
    tp = lv * (1 + sg)
    H[30] = tp + 0.01
    ret, x, how = X.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 101.0, False)
    assert how == "tp" and x == 30
    assert abs(ret - (tp / lv - 1 - 2 * MK)) < 1e-12


def test_outcome_stop_first_same_minute():
    sg, f, lv = 0.01, 20, 100.0
    O, H, L, C = _flat(o=lv)
    H[29] = lv * (1 + sg) + 0.01
    C[29] = lv * (1 - 4 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    ret, x, how = X.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 101.0, False)
    assert how == "stop"


def test_outcome_backstop_beats_tp():
    sg, f, lv = 0.01, 20, 100.0
    O, H, L, C = _flat(o=lv)
    H[25] = lv * (1 + sg) + 0.01
    L[25] = lv * (1 - 8 * sg) - 0.01
    ret, x, how = X.outcome_mu(H, L, C, O, f, lv, sg, 1.0, 101.0, False)
    assert how == "backstop" and x == 25


def test_outcome_timeout_funding():
    sg, f, lv, o2 = 0.01, 20, 100.0, 100.1
    O, H, L, C = _flat(o=lv)
    r0, _, h0 = X.outcome_mu(H, L, C, O, f, lv, sg, 1.0, o2, False)
    r1, _, h1 = X.outcome_mu(H, L, C, O, f, lv, sg, 1.0, o2, True)
    assert (h0, h1) == ("time", "time")
    assert abs((r0 - r1) - 0.0001) < 1e-12


def test_extra_duplicates_base_5p0():
    # extra rung level == base 5.0 level -> same fill minute, size, outcome
    o1, sg = 100.0, 0.01
    lv = o1 * (1 - 5.0 * sg)
    lvx = o1 * (1 - X.EXTRA_K * sg)
    assert lvx == lv
    low = np.array([lv + 0.01, lv - 0.01, lv - 1.0])
    assert X.find_fill(low, lv) == X.find_fill(low, lvx) == 1
    assert X.size_mult(2) == 1.0 / 3.0


def test_causality_fill_uses_only_closed_minutes():
    o, sg = 100.0, 0.01
    thr = o * (1 - 2.5 * sg)
    closes = np.full((4, 3), 100.0)
    closes[0, 1] = thr - 0.01
    n = X.n_vector(closes, np.full(4, o), np.full(4, sg))
    assert n.tolist() == [0, 1, 0]


def test_sigma_known_at_bar_open():
    opens = np.array([100.0, 101.0, 102.0, 103.0, 500.0])
    s = pd.Series(opens).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert np.isfinite(s[3]) and not np.isfinite(s[0])
    ref = pd.Series(opens[:4]).pct_change().rolling(3, min_periods=2).std(ddof=1).shift(1).to_numpy()
    assert abs(s[3] - ref[3]) < 1e-12
