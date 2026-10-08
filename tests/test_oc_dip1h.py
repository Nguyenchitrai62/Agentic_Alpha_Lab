"""oc_dip1h tests: causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_dip1h.py -q
Covers research/tournament/oc_dip1h/dip1h_core.py (PLAN.md frozen 2026-10-08).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research/tournament/oc_dip1h"))
import dip1h_core as C


def _flat_bar(o0=100.0):
    O = np.full(60, o0)
    H = np.full(60, o0)
    L = np.full(60, o0)
    return O, H, L


def _neutral_bar(o0=100.0, h=97.6):
    """Bar whose highs can never TP a k=2.5 fill at sg=0.01 (TP=98.475)."""
    O, H, L = _flat_bar(o0)
    H[:] = h
    return O, H, L


def test_no_fill_in_first_five_minutes():
    # Dip below every bid only in minutes 0..4 -> no trade (pipeline delay).
    O, H, L = _flat_bar()
    L[2] = 90.0  # through the deepest bid, but minute 2 is excluded
    H[2] = 100.0
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    assert out == [], out


def test_equality_never_fills():
    # low == bid exactly is NOT a trade-through (strict <).
    O, H, L = _flat_bar()
    bid25 = 100.0 * (1 - 2.5 * 0.01)  # 97.5
    L[10] = bid25
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    assert out == [], out


def test_fill_uses_only_data_up_to_fill_minute():
    # TP level touched in the SAME minute as the fill must not exit the rung:
    # the exit scan starts at f+1.
    O, H, L = _neutral_bar()
    L[10] = 97.4   # fill k=2.5 at 97.5
    H[10] = 99.0   # above TP 98.475, but same minute -> ignored
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    assert len(out) == 1 and out[0]["how"] == "time", out
    assert out[0]["f"] == 10 and out[0]["x"] == 60


def test_stop_first_on_same_minute_tie():
    # Minute 12 has low <= stop AND high > TP -> stop wins (k=2.5 rung).
    O, H, L = _neutral_bar()
    L[10] = 97.4  # fill k=2.5 @97.5; stop=93.6, tp=98.475
    L[12] = 93.0
    O[12] = 94.0
    H[12] = 99.0
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    r = out[0]
    assert r["k"] == 2.5 and r["how"] == "stop", out
    assert r["exit"] == 93.6  # min(stop, open)=min(93.6,94.0)


def test_sigma_excludes_current_and_future_bars():
    # Flat opens then a jump AT bar j: sg[j] must equal the pre-jump std.
    o = np.full(800, 100.0)
    o[799] = 200.0  # jump inside bar 799's formation -> must not leak into sg[799]
    sg = C.sigma1h_causal(o)
    assert np.isnan(sg[119])  # only 119 prior returns < min 120
    assert np.isnan(sg[120])  # lr[0] is NaN: 119 valid < min 120
    assert abs(sg[121]) < 1e-12  # 120 flat returns -> std 0
    assert abs(sg[799]) < 1e-12, sg[799]  # jump excluded (uses bars < 799)
    # After the jump it enters causally:
    assert sg[800 - 1] is not None and np.isfinite(sg[799 + 0])
    lr = np.log(2.0)
    # sg[800] would need index 800 (out of range); check shift logic on longer series
    o2 = np.full(802, 100.0)
    o2[799] = 200.0
    sg2 = C.sigma1h_causal(o2)
    manual = np.std([0.0] * 719 + [lr], ddof=1)
    assert abs(sg2[800] - manual) < 1e-12, (sg2[800], manual)


def test_handcheck_tp_return():
    O, H, L = _neutral_bar()
    L[10] = 97.4
    H[12] = 98.5  # > TP 98.475
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    assert len(out) == 1
    r = out[0]
    assert r["how"] == "tp" and r["f"] == 10 and r["x"] == 12
    assert abs(r["fill"] - 97.5) < 1e-9
    assert abs(r["exit"] - 97.5 * 1.01) < 1e-9
    assert abs(r["ret"] - (0.01 - 2 * C.MAKER)) < 1e-12


def test_handcheck_stop_gap_fill():
    O, H, L = _neutral_bar()
    L[10] = 97.4  # fill k=2.5 @97.5, stop 93.6
    O[15] = 93.0  # gaps through the stop
    L[15] = 92.0
    H[15] = 93.5
    out = C.bar_outcomes(100.0, O, H, L, 0.01, 100.0, False)
    r = out[0]  # k=2.5 rung (deeper rungs also fill at minute 15)
    assert r["k"] == 2.5 and r["how"] == "stop"
    assert r["exit"] == 93.0  # min(stop, open)
    assert abs(r["ret"] - (93.0 / 97.5 - 1 - C.MAKER - C.TAKER)) < 1e-12


def test_handcheck_timeout_funding():
    O, H, L = _neutral_bar()
    L[10] = 97.4  # fill @97.5, never stopped/TP'd
    o_next = 98.0
    r_set = C.bar_outcomes(100.0, O, H, L, 0.01, o_next, True)[0]
    r_nos = C.bar_outcomes(100.0, O, H, L, 0.01, o_next, False)[0]
    assert r_set["how"] == "time" and r_set["x"] == 60
    assert abs(r_set["ret"] - (98.0 / 97.5 - 1 - C.MAKER - C.TAKER - C.FUND)) < 1e-12
    assert abs(r_nos["ret"] - (98.0 / 97.5 - 1 - C.MAKER - C.TAKER)) < 1e-12


def test_size_constants_match_plan():
    assert abs(C.SIZE_G2 - (0.25 / 4.0 / 1.657) * 1.7) < 1e-12
    assert abs(C.SIZE["H05"] - C.SIZE_G2 * 0.5) < 1e-15
    assert abs(C.SIZE["H025"] - C.SIZE_G2 * 0.25) < 1e-15
    assert tuple(C.RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)


def test_metric_helpers():
    assert abs(C.pct_per_month(1.0) - 0.0) < 1e-12
    assert abs(C.pct_per_month(1.05 ** 12) - 5.0) < 1e-9
    assert abs(C.max_dd(np.array([1.0, 1.1, 1.2, 1.3]))) < 1e-12
    dd = C.max_dd(np.array([1.0, 1.1, 1.05, 1.2]))
    assert abs(dd - 100 * (1 - 1.05 / 1.1)) < 1e-12
    dd2 = C.max_dd(np.array([1.0, 1.2, 1.08, 1.3]))
    assert abs(dd2 - 100 * (1 - 1.08 / 1.2)) < 1e-12
