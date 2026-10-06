"""Tests for oc_i2_tapecancel (IDEAS2_20261007 §3 tape-contingent dip-bid cancel).

Synthetic hand checks only; no market data, no fitting, fast.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_i2_tapecancel"))
import tapecancel as T

HERE = ROOT / "research/tournament/oc_i2_tapecancel"


def test_frozen_constants():
    assert T.MAKER == 0.0002 and T.TAKER == 0.00055 and T.FUND == 0.0001
    assert T.RUNGS == (2.5, 3.0, 3.5, 4.0, 5.0)
    assert (T.LIVE_A, T.LIVE_B) == (16, 238)
    assert T.PLACEMENT_MIN == 16
    assert T.CANCEL1_MIN == 46 and T.CANCEL2_MIN == 76  # +30m / +60m
    assert T.WIN1 == (17, 46) and T.WIN2 == (17, 76)
    assert (T.WIN1[1] - T.WIN1[0] + 1) == 30
    assert (T.WIN2[1] - T.WIN2[0] + 1) == 60
    assert T.MIN_SAMPLES == 30 and T.TRAIL_DAYS == 30


def test_tape_sell_share_basic():
    buy = np.array([70.0, 30.0])
    sell = np.array([20.0, 80.0])
    assert T.tape_sell_share(buy, sell) == 0.5  # 100/200


def test_tape_sell_share_invalid():
    assert np.isnan(T.tape_sell_share(np.array([1.0, np.nan]), np.array([1.0, 1.0])))
    assert np.isnan(T.tape_sell_share(np.array([0.0]), np.array([0.0])))  # zero total
    assert np.isnan(T.tape_sell_share(np.array([]), np.array([])))
    assert np.isnan(T.tape_sell_share(np.array([1.0]), np.array([1.0, 2.0])))  # shape


def test_trailing_quantile_window():
    day = 86_400_000_000_000
    bar = 1_000 * day
    # samples every 4h for 40d ending 5h before bar
    opens = np.arange(bar - 40 * day, bar - 5 * 3_600_000_000_000, 4 * 3_600_000_000_000)
    s = np.linspace(0.0, 1.0, len(opens))
    q = T.trailing_quantile(opens, s, bar, 0.80)
    lo, hi = bar - 30 * day, bar - 4 * 3_600_000_000_000
    expect = np.quantile(s[(opens >= lo) & (opens <= hi)], 0.80)
    assert q == expect
    # a sample 1 minute after hi must not leak in
    late_o = np.append(opens, np.array([hi + 60_000_000_000]))
    late_s = np.append(s, np.array([999.0]))
    assert T.trailing_quantile(late_o, late_s, bar, 0.80) == expect


def test_trailing_quantile_min_samples():
    day = 86_400_000_000_000
    bar = 1_000 * day
    opens = np.arange(bar - 4 * day, bar - 5 * 3_600_000_000_000, 4 * 3_600_000_000_000)
    s = np.full(len(opens), 0.6)
    assert len(opens) < 30
    assert np.isnan(T.trailing_quantile(opens, s, bar, 0.80))  # < 30 samples
    many_o = np.arange(bar - 30 * day, bar - 4 * 3_600_000_000_000, 3_600_000_000_000)
    many_s = np.full(len(many_o), 0.6)
    assert T.trailing_quantile(many_o, many_s, bar, 0.80) == 0.6


def test_cancelled_boundaries():
    # C1: f<=46 always kept; f=47 cancelled only when strictly toxic
    assert T.cancelled(46, 0.99, 0.10, T.CANCEL1_MIN) is False
    assert T.cancelled(47, 0.11, 0.10, T.CANCEL1_MIN) is True
    assert T.cancelled(47, 0.10, 0.10, T.CANCEL1_MIN) is False  # equality: no cancel
    assert T.cancelled(47, 0.09, 0.10, T.CANCEL1_MIN) is False
    assert T.cancelled(47, float("nan"), 0.10, T.CANCEL1_MIN) is False
    assert T.cancelled(47, 0.11, float("nan"), T.CANCEL1_MIN) is False
    # C2: f<=76 kept; f=77 toxic -> cancelled
    assert T.cancelled(76, 0.99, 0.10, T.CANCEL2_MIN) is False
    assert T.cancelled(77, 0.11, 0.10, T.CANCEL2_MIN) is True
    assert T.cancelled(238, 0.11, 0.10, T.CANCEL2_MIN) is True


def test_find_fill_strict():
    assert T.find_fill(np.array([1.0, 0.5, 0.4]), 0.5) == 2  # strict <: equal never fills
    assert T.find_fill(np.array([np.nan, 0.1]), 0.5) == 1
    assert T.find_fill(np.array([0.6, 0.7]), 0.5) is None


def test_outcome_stop_first_priority():
    # flat tape: TP at +1sg never touched, stop triggers -> stop leg
    n = 240
    lv, sg = 100.0, 0.01
    sl = lv * (1 - 4 * sg)
    Ha = np.full(n, lv * 1.001)
    La = np.full(n, lv * 0.999)
    Ca = np.full(n, lv * 0.999)
    Ca[20] = sl  # close below stop on a clock minute with (m+1)%5==0?
    Oa = np.full(n, lv)
    f = 16
    # minute offsets are bar offsets; find a valid stop minute post-fill
    m = None
    for cand in range(f + 1, 239):
        if (cand + 1) % 5 == 0:
            m = cand
            break
    Ca[:] = lv * 0.999
    Ca[m] = sl
    Oa[m + 1] = sl * 0.999
    ret, x, how = T.outcome_from_fill(Ha, La, Ca, Oa, f, lv, sg, lv * 1.0, False)
    assert how == "stop" and x == m + 1
    assert ret == Oa[m + 1] / lv - 1 - T.MAKER - T.TAKER


def test_gross_cap_walk_cut_skip_order():
    f = np.array([10, 20, 30])
    x = np.array([100, 100, 100])
    w = np.array([1.0, 1.0, 1.0])
    kept = T.gross_cap_weights(f, x, w, [0, 1, 2], G=2.0)
    assert kept == {0: 1.0, 1: 1.0, 2: 0.0}  # third skipped when full
    kept = T.gross_cap_weights(f, x, np.array([1.5, 1.5, 1.5]), [0, 1, 2], G=2.0)
    assert kept[0] == 1.5 and kept[1] == 0.5 and kept[2] == 0.0  # cut to room
    # exited fills free room: x<=f is observably closed
    kept = T.gross_cap_weights(np.array([10, 50]), np.array([20, 100]),
                               np.array([2.0, 2.0]), [0, 1], G=2.0)
    assert kept == {0: 2.0, 1: 2.0}


def test_choose_variant_dev_only():
    # eligible: dd 4/4 + sums >=3/4; pick highest WORST-year delta
    stats = {"C1": {"years_sum_ge": 3, "years_dd_ok": 4,
                    "worst_delta_dev4": 0.05, "dSum_dev4": 0.30},
             "C2": {"years_sum_ge": 4, "years_dd_ok": 4,
                    "worst_delta_dev4": 0.02, "dSum_dev4": 0.50}}
    assert T.choose_variant(stats) == "C1"  # worst-year beats mean
    stats["C1"]["worst_delta_dev4"] = 0.02
    stats["C1"]["dSum_dev4"] = 0.60
    assert T.choose_variant(stats) == "C1"  # tie on worst -> higher mean
    stats["C2"]["years_dd_ok"] = 3
    stats["C1"]["years_sum_ge"] = 2
    assert T.choose_variant(stats) is None  # nobody eligible


def test_baseline_numbers_reproduced():
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    v = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0, g25 = cc["rows"]["G2_f0.0"], cc["rows"]["G2_f0.25"]
    assert (g25["R"], g25["DD"], g25["full_path_dd"]["full"]) == (5.634, 16.75, 16.66)
    assert (g0["R"], g0["W"], g0["DD"]) == (v["R"], v["W"], v["DD"]) == (5.41, 2.588, 16.91)


def test_preregistration_present():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    assert "C1" in rep and "C2" in rep
    assert "+30m" in rep and "p80" in rep and "+60m" in rep and "p90" in rep
    assert "+0.273" in rep
    assert "ONLY" in rep and "2021-2024" in rep  # dev-only selection
    assert "2025-09-24..2026-09-23" in rep and "POST-HOC" in rep
