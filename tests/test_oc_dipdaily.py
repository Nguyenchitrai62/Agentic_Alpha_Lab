"""oc_dipdaily tests: causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_dipdaily.py -q
Covers research/tournament/oc_dipdaily/dipdaily_core.py (PLAN.md frozen 2026-10-08).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research/tournament/oc_dipdaily"))
import dipdaily_core as C


def _flat_day(o0=100.0):
    O = np.full(1440, o0)
    H = np.full(1440, o0)
    L = np.full(1440, o0)
    return O, H, L


def _neutral_day(o0=100.0, h=97.6):
    """Day whose highs can never TP a k=2.5 fill at sg=0.01 (TP=98.475)."""
    O, H, L = _flat_day(o0)
    H[:] = h
    return O, H, L


def test_no_fill_in_first_five_minutes():
    # Dip below every bid only in minutes 0..4 -> no trade (pipeline delay).
    O, H, L = _flat_day()
    L[2] = 90.0  # through the deepest bid, but minute 2 is excluded
    H[2] = 100.0
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    assert out == [], out


def test_equality_never_fills():
    # low == bid exactly is NOT a trade-through (strict <).
    O, H, L = _flat_day()
    bid25 = 100.0 * (1 - 2.5 * 0.01)  # 97.5
    L[10] = bid25
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    assert out == [], out


def test_fill_uses_only_data_up_to_fill_minute():
    # TP level touched in the SAME minute as the fill must not exit the rung:
    # the exit scan starts at f+1.
    O, H, L = _neutral_day()
    L[10] = 97.4   # fill k=2.5 at 97.5
    H[10] = 99.0   # above TP 98.475, but same minute -> ignored
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    assert len(out) == 1 and out[0]["how"] == "time", out
    assert out[0]["f"] == 10 and out[0]["x"] == 1440
    assert out[0]["nst"] == 3  # timeout always spans 08/16/24h


def test_stop_first_on_same_minute_tie():
    # Minute 12 has low <= stop AND high > TP -> stop wins (k=2.5 rung).
    O, H, L = _neutral_day()
    L[10] = 97.4  # fill k=2.5 @97.5; stop=93.6, tp=98.475
    L[12] = 93.0
    O[12] = 94.0
    H[12] = 99.0
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    r = out[0]
    assert r["k"] == 2.5 and r["how"] == "stop", out
    assert r["exit"] == 93.6  # min(stop, open)=min(93.6,94.0)
    assert r["nst"] == 0  # no settlement in (10, 12]


def test_sigma_excludes_current_and_future_bars():
    # Flat opens then a jump AT day j: sg[j] must equal the pre-jump std.
    o = np.full(200, 100.0)
    o[199] = 200.0  # jump inside day 199's formation -> must not leak into sg[199]
    sg = C.sigma1d_causal(o)
    assert np.isnan(sg[60])  # raw[59]: 59 valid < min 60
    assert abs(sg[61]) < 1e-12  # raw[60]: 60 flat returns -> std 0
    assert abs(sg[199]) < 1e-12, sg[199]  # jump excluded (uses days < 199)
    o2 = np.full(202, 100.0)
    o2[199] = 200.0
    sg2 = C.sigma1d_causal(o2)
    lr = np.log(2.0)
    manual = np.std([0.0] * 119 + [lr], ddof=1)
    assert abs(sg2[200] - manual) < 1e-12, (sg2[200], manual)


def test_count_settlements():
    assert C.count_settlements(10, 12) == 0
    assert C.count_settlements(100, 500) == 1  # 08:00 only
    assert C.count_settlements(100, 1000) == 2  # 08:00 + 16:00
    assert C.count_settlements(10, 1439) == 2  # 1440 excluded
    assert C.count_settlements(5, 1440) == 3  # full-day hold
    assert C.count_settlements(1000, 1440) == 1  # only 24:00 left


def test_handcheck_tp_return_no_funding():
    O, H, L = _neutral_day()
    L[10] = 97.4
    H[12] = 98.5  # > TP 98.475
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    assert len(out) == 1
    r = out[0]
    assert r["how"] == "tp" and r["f"] == 10 and r["x"] == 12
    assert abs(r["fill"] - 97.5) < 1e-9
    assert abs(r["exit"] - 97.5 * 1.01) < 1e-9
    assert r["nst"] == 0
    assert abs(r["ret"] - (0.01 - 2 * C.MAKER)) < 1e-12


def test_handcheck_tp_return_one_settlement():
    O, H, L = _neutral_day()
    L[100] = 97.4  # fill k=2.5 @97.5
    H[500] = 98.5  # TP; spans the 08:00 settlement (minute 480)
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    r = out[0]
    assert r["how"] == "tp" and r["x"] == 500 and r["nst"] == 1, r
    assert abs(r["ret"] - (0.01 - 2 * C.MAKER - C.FUND)) < 1e-12


def test_handcheck_stop_gap_fill_two_settlements():
    O, H, L = _neutral_day()
    L[100] = 97.4  # fill k=2.5 @97.5, stop 93.6
    O[1000] = 94.0  # gaps through the stop; spans 08:00 + 16:00
    L[1000] = 92.0
    H[1000] = 93.5
    out = C.day_outcomes(100.0, O, H, L, 0.01, 100.0)
    r = out[0]  # k=2.5 rung (deeper rungs also fill at minute 1000)
    assert r["k"] == 2.5 and r["how"] == "stop" and r["nst"] == 2, r
    assert r["exit"] == 93.6  # min(stop, open)
    assert abs(r["ret"] - (93.6 / 97.5 - 1 - C.MAKER - C.TAKER
                           - 2 * C.FUND)) < 1e-12


def test_handcheck_timeout_funding():
    O, H, L = _neutral_day()
    L[10] = 97.4  # fill @97.5, never stopped/TP'd
    o_next = 98.0
    r = C.day_outcomes(100.0, O, H, L, 0.01, o_next)[0]
    assert r["how"] == "time" and r["x"] == 1440 and r["nst"] == 3
    assert abs(r["ret"] - (98.0 / 97.5 - 1 - C.MAKER - C.TAKER
                           - 3 * C.FUND)) < 1e-12


def test_missing_next_open_skips_day():
    O, H, L = _neutral_day()
    L[10] = 97.4
    assert C.day_outcomes(100.0, O, H, L, 0.01, np.nan) == []
    assert C.day_outcomes(np.nan, O, H, L, 0.01, 100.0) == []
    assert C.day_outcomes(100.0, O, H, L, np.nan, 100.0) == []


def test_size_constants_match_plan():
    assert abs(C.SIZE_G2 - (0.25 / 4.0 / 1.657) * 1.7) < 1e-12
    assert abs(C.SIZE["D05"] - C.SIZE_G2 * 0.5) < 1e-15
    assert abs(C.SIZE["D025"] - C.SIZE_G2 * 0.25) < 1e-15
    assert tuple(C.RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)


def test_metric_helpers():
    assert abs(C.pct_per_month(1.0) - 0.0) < 1e-12
    assert abs(C.pct_per_month(1.05 ** 12) - 5.0) < 1e-9
    # partial-leg norm: E over 77 days
    e = 1.02
    assert abs(C.pct_per_month(e, 77) - 100 * (e ** (30.4375 / 77) - 1)) < 1e-12
    assert abs(C.max_dd(np.array([1.0, 1.1, 1.2, 1.3]))) < 1e-12
    dd = C.max_dd(np.array([1.0, 1.1, 1.05, 1.2]))
    assert abs(dd - 100 * (1 - 1.05 / 1.1)) < 1e-12
