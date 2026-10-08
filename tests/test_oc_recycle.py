"""Tests for oc_recycle (IDEAS6 #8 winner-recycled dip capital).

Pure-numpy core checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_recycle.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_recycle"))

from recycle import (GROSS_CAP, MAKER, TAKER, committed_walk, find_fill,
                     n_vector, outcome_from_fill, recycle_walk, size_mult)

PX = 100.0
SG = 0.01
SL = PX * (1 - 4 * SG)  # 96
BL = PX * (1 - 8 * SG)  # 92
TP = PX * (1 + 1.0 * SG)  # 101


def test_find_fill_strict_and_nan():
    assert find_fill(np.array([100.0, 100.0, 99.9]), np.full(3, 100.0)) == 2
    assert find_fill(np.array([100.0, 100.0]), np.full(2, 100.0)) is None
    assert find_fill(np.array([np.nan, 99.0]), np.full(2, 100.0)) == 1


def test_n_vector_nan_safe_and_exact_flush():
    close = np.array([[np.nan, 90.0]])
    assert list(n_vector(close, np.array([100.0]), np.array([0.01]))) == [0, 1]
    # flush at exactly 2.5 sigma counts: thr = 100*(1-2.5*0.01) = 97.5
    close = np.array([[97.5]])
    assert list(n_vector(close, np.array([100.0]), np.array([0.01]))) == [1]


def test_size_mult():
    assert size_mult(0) == pytest.approx(1.0)
    assert size_mult(4) == pytest.approx(0.2)


def test_outcome_tp_handcheck():
    # TP touched at f+1, no stop/backstop -> maker TP.
    Ha = np.full(240, 100.5)
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    Ha[51] = 101.5  # f=50 -> first post minute 51, high > 101 strictly
    ret, x, how = outcome_from_fill(Ha, La, Ca, Oa, 50, PX, SG, 100.0, False)
    assert how == "tp" and x == 51
    assert ret == pytest.approx(TP / PX - 1 - 2 * MAKER)


def test_outcome_stop_first_same_minute():
    # Same minute: backstop touch + TP touch -> backstop wins (stop-first).
    Ha = np.full(240, 100.5)
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    La[61] = 91.0   # low <= 92 backstop
    Ha[61] = 102.0  # high > 101 TP, same minute
    Oa[61] = 100.0
    ret, x, how = outcome_from_fill(Ha, La, Ca, Oa, 60, PX, SG, 100.0, False)
    assert how == "backstop" and x == 61
    assert ret == pytest.approx(min(BL, 100.0) / PX - 1 - MAKER - TAKER)


def test_truncation_invariance():
    # Appending minutes beyond the bar + changing far-future data cannot move
    # an outcome decided inside the bar (causality / truncation test).
    rng = np.random.default_rng(7)
    Ha = 100 + rng.normal(0, 0.5, 240)
    La = Ha - np.abs(rng.normal(0, 0.3, 240))
    Ca = 100 + rng.normal(0, 0.3, 240)
    Oa = 100 + rng.normal(0, 0.3, 240)
    Ha[80] = 105.0  # force TP at 80 for f=50
    r1 = outcome_from_fill(Ha, La, Ca, Oa, 50, PX, SG, 100.0, False)
    Ha2 = np.concatenate([Ha, 90 + rng.normal(0, 5, 60)])
    La2 = np.concatenate([La, 80 + rng.normal(0, 5, 60)])
    Ca2 = np.concatenate([Ca, 80 + rng.normal(0, 5, 60)])
    Oa2 = np.concatenate([Oa, 80 + rng.normal(0, 5, 60)])
    r2 = outcome_from_fill(Ha2, La2, Ca2, Oa2, 50, PX, SG, 100.0, False)
    assert r1 == r2
    # Banning the prefix (minutes < 16) is structural: live window starts at 16.
    assert r1[1] >= 16


def test_committed_walk_binds_and_cuts():
    # G=1.0, two full-size fills: first kept whole, second cut to room 0.
    F, X, W = [16, 100], [30, 200], [1.0, 1.0]
    kept = committed_walk(F, X, W, [0, 1], G=1.0)
    assert kept[0] == pytest.approx(1.0)
    assert kept[1] == pytest.approx(0.0)  # room 0 -> skipped


def test_recycle_v2_frees_winner_for_next_signal():
    # Hand check: G=1.0 committed. Signal A (BTC) fills at 16, TPs at 30
    # (realised before signal B at f=100). Base skips B (committed 1.0).
    # V2 recycles A's freed 1.0 -> keeps B. V1 same-coin: B is ETH -> skipped.
    F = [16, 100]
    X = [30, 200]
    W = [1.0, 1.0]
    HW = ["tp", "time"]
    SY = ["BTCUSDT", "ETHUSDT"]
    kb, kind_b = recycle_walk(F, X, W, HW, SY, [0, 1], G=1.0, same_coin=False)
    assert kb[0] == pytest.approx(1.0) and kind_b[0] == 0
    assert kb[1] == pytest.approx(1.0) and kind_b[1] == 1  # recycled
    k1, kind1 = recycle_walk(F, X, W, HW, SY, [0, 1], G=1.0, same_coin=True)
    assert k1[0] == pytest.approx(1.0)
    assert k1[1] == pytest.approx(0.0)  # other-coin winner does not fund ETH


def test_recycle_same_coin_v1_keeps():
    F = [16, 100]
    X = [30, 200]
    W = [1.0, 1.0]
    HW = ["tp", "time"]
    SY = ["BTCUSDT", "BTCUSDT"]
    k1, kind1 = recycle_walk(F, X, W, HW, SY, [0, 1], G=1.0, same_coin=True)
    assert k1[1] == pytest.approx(1.0) and kind1[1] == 1


def test_loser_never_frees_and_no_compounding():
    # A stops (loser) -> B skipped even in V2 (winners only).
    F = [16, 100]
    X = [30, 200]
    W = [1.0, 1.0]
    HW = ["stop", "time"]
    SY = ["BTCUSDT", "ETHUSDT"]
    k2, _ = recycle_walk(F, X, W, HW, SY, [0, 1], G=1.0, same_coin=False)
    assert k2[1] == pytest.approx(0.0)
    # No compounding: recycled fill's own TP frees nothing for a third signal.
    F = [16, 100, 150]
    X = [30, 120, 220]
    W = [1.0, 1.0, 1.0]
    HW = ["tp", "tp", "time"]
    SY = ["BTCUSDT", "BTCUSDT", "BTCUSDT"]
    k1, kind1 = recycle_walk(F, X, W, HW, SY, [0, 1, 2], G=1.0, same_coin=True)
    assert k1[1] == pytest.approx(1.0) and kind1[1] == 1  # recycled via A
    # B is recycled (kind 1) so its TP frees nothing; C needs B's money -> skip.
    # (A's unit is consumed by B: one recycle per unit.)
    assert k1[2] == pytest.approx(0.0)


def test_unrealised_tp_does_not_free():
    # A's TP exits at x=150, AFTER B's fill at f=100 -> not realised, no free.
    F = [16, 100]
    X = [150, 200]
    W = [1.0, 1.0]
    HW = ["tp", "time"]
    SY = ["BTCUSDT", "BTCUSDT"]
    k1, _ = recycle_walk(F, X, W, HW, SY, [0, 1], G=1.0, same_coin=True)
    assert k1[1] == pytest.approx(0.0)


def test_gross_cap_default():
    assert GROSS_CAP == 2.0
