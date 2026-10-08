"""Tests for oc_tapepeg (IDEAS6 #4 tape-anchored rung placement).

Pure-numpy core checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_tapepeg.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_tapepeg"))

from tapepeg import (MAKER, TAKER, find_fill, n_vector, outcome_mu, rung_px,
                     tape_peg, trailing_low)

PX = 100.0
SG = 0.01
TP = PX * (1 + 1.0 * SG)  # 101


def test_find_fill_strict():
    assert find_fill(np.array([100.0, 100.0, 99.9]), 100.0) == 2
    assert find_fill(np.array([100.0, 100.0]), 100.0) is None  # == never fills
    assert find_fill(np.array([np.nan, 99.0]), 100.0) == 1  # NaN never fills


def test_n_vector_nan_safe():
    close = np.array([[np.nan, 90.0]])
    assert list(n_vector(close, np.array([100.0]), np.array([0.01]))) == [0, 1]


def test_trailing_low_ignores_nan():
    assert trailing_low(np.array([np.nan, 99.0, 101.0])) == pytest.approx(99.0)
    assert not np.isfinite(trailing_low(np.array([np.nan, np.nan])))
    assert not np.isfinite(trailing_low(np.array([])))


def test_tape_peg_handcheck():
    # LOW60 = 100 -> tick 0.01, peg1 = 99.99, grid 0.05, peg2 = floor(99.99/0.05)*0.05.
    p1, p2 = tape_peg(100.0)
    assert p1 == pytest.approx(99.99)
    assert p2 == pytest.approx(np.floor(99.99 / 0.05) * 0.05)
    assert p2 < p1 < 100.0
    p1b, p2b = tape_peg(np.nan)
    assert not np.isfinite(p1b) and not np.isfinite(p2b)
    p1c, p2c = tape_peg(-5.0)
    assert not np.isfinite(p1c) and not np.isfinite(p2c)


def test_rung_px_min_and_fallback():
    # Sigma price 97 (k=3, O=100, sg=0.01); LOW60 deep at 95 -> peg binds.
    b, v1, v2 = rung_px(100.0, 0.01, 3.0, 95.0)
    assert b == pytest.approx(97.0)
    assert v1 == pytest.approx(95.0 * 0.9999)
    assert v2 == pytest.approx(95.0 * 0.9995)
    assert v2 < v1 < b
    # LOW60 shallow at 99 -> sigma price survives (min keeps the deeper sigma rung).
    b2, v12, v22 = rung_px(100.0, 0.01, 3.0, 99.0)
    assert b2 == pytest.approx(97.0)
    assert v12 == pytest.approx(97.0) and v22 == pytest.approx(97.0)
    # All-NaN LOW60 -> fallback to sigma price.
    b3, v13, v23 = rung_px(100.0, 0.01, 3.0, np.nan)
    assert (b3, v13, v23) == (pytest.approx(97.0), pytest.approx(97.0), pytest.approx(97.0))


def test_rung_px_v2_rounds_down_to_5tick():
    # peg1 must sit on the 1-tick grid edge and peg2 on the 5-tick grid.
    low = 100.0
    p1, p2 = tape_peg(low)
    tick = low * 0.0001
    assert (low - p1) == pytest.approx(tick)
    assert abs(p1 - round(p1 / tick) * tick) < 1e-9
    assert abs(p2 - np.floor(p1 / (5 * tick)) * (5 * tick)) < 1e-9
    assert p2 <= p1


def test_outcome_mu_timeout_handcheck():
    Ha = np.full(240, 100.5)
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    ret, x, how = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 100.0, False)
    assert how == "time" and x == 240
    assert ret == pytest.approx(100.0 / PX - 1 - MAKER - TAKER)


def test_outcome_mu_tp_handcheck():
    Ha = np.full(240, 100.0)
    Ha[110] = 102.0  # f=100 => minute 110 touches TP=101 strictly
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    ret, x, how = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 100.0, False)
    assert how == "tp"
    assert ret == pytest.approx(TP / PX - 1 - 2 * MAKER)


def test_truncation_peg_ignores_placement_window():
    # Moving 1m lows inside the live window must not move the peg.
    before = np.full(60, 100.0)
    assert trailing_low(before) == pytest.approx(100.0)
    # A crash AFTER T (placement window) is not an input to trailing_low by
    # construction: the caller slices [base-60, base), so assert the slice math.
    base = 1000
    lo, hi = base - 60, base
    assert (lo, hi) == (940, 1000)
    assert hi <= base  # strictly before T; minute `base` itself excluded
    # Scrambling the tape AFTER the exit cannot change the outcome: TP at 110,
    # so minutes 120+ are never read.
    Ha = np.full(240, 100.0)
    Ha[110] = 102.0  # f=100 => minute 110 touches TP=101 strictly
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    ref = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 100.0, False)
    assert ref[2] == "tp"
    Ha2 = Ha.copy()
    Ha2[120:] = 0.01
    La2 = La.copy()
    La2[120:] = 0.01
    assert outcome_mu(Ha2, La2, Ca, Oa, 100, PX, SG, 1.0, 100.0, False) == ref


def test_nan_window_never_triggers():
    low = np.array([np.nan, np.nan])
    assert find_fill(low, 100.0) is None


def test_results_schema_if_present():
    p = ROOT / "research/tournament/oc_tapepeg/results.json"
    if not p.exists():
        pytest.skip("heavy run not done yet")
    res = json.loads(p.read_text())
    assert res["n_fills"] > 15000
    for tag in ("V1", "V2"):
        assert "dec" in res[tag] and "gate_pass" in res[tag]
        d = res[tag]["dec"]
        assert d["years_sum_ge"] <= 5 and d["years_dd_ok"] <= 5
        assert "dSum5y" in d
    assert 0.0 <= res["peg_bind"]["V1_share"] <= 1.0
