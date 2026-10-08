"""Tests for oc_makerexit (IDEAS6 #1 maker-only timeout exit).

Pure-numpy core checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_makerexit.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_makerexit"))

from makerexit import (DELTA1, DELTA3, FUND, MAKER, TAKER, WIN_END,
                       WIN_LIVE_A, find_fill, n_vector, outcome_maker_window,
                       outcome_mu, outcome_pair_maker)

PX = 100.0
SG = 0.01
SL = PX * (1 - 4 * SG)  # 96
BL = PX * (1 - 8 * SG)  # 92
TP = PX * (1 + 1.0 * SG)  # 101


def flat_window(n=60, o=100.0, h=100.0, l=100.0, c=100.0):
    return (np.full(n, h), np.full(n, l), np.full(n, c), np.full(n, o))


def test_find_fill_strict():
    assert find_fill(np.array([100.0, 100.0, 99.9]), 100.0) == 2
    assert find_fill(np.array([100.0, 100.0]), 100.0) is None  # == never fills
    assert find_fill(np.array([np.nan, 99.0]), 100.0) == 1  # NaN never fills


def test_n_vector_nan_safe():
    close = np.array([[np.nan, 90.0]])
    assert list(n_vector(close, np.array([100.0]), np.array([0.01]))) == [0, 1]


def test_outcome_mu_timeout_handcheck():
    # Flat market at px: no TP (need >101), no stop (need close<=96 on clock),
    # no backstop -> timeout at o2=100 taker, no settle.
    Ha = np.full(240, 100.5)
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    ret, x, how = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 100.0, False)
    assert how == "time" and x == 240
    assert ret == pytest.approx(100.0 / PX - 1 - MAKER - TAKER)


def test_maker_fill_handcheck():
    # Timeout then high touches above P1=100.01 at minute 250 -> maker at P1.
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005)
    Hw[10] = 100.02  # absolute minute 250
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "maker" and x == 250
    assert ret == pytest.approx(P1 / PX - 1 - 2 * MAKER)
    # improvement over taker timeout = price +1bp plus fee save 3.5bps
    base = o2 / PX - 1 - MAKER - TAKER
    assert (ret - base) == pytest.approx(DELTA1 + (TAKER - MAKER))


def test_maker_strict_no_touch_on_equal():
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=P1)  # high == P exactly -> NO fill
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "remainder" and x == WIN_END
    assert ret == pytest.approx(100.0 / PX - 1 - MAKER - TAKER)


def test_minute5_ban():
    # Huge high inside banned minutes 240..244 must NOT fill.
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005)
    Hw[0] = 200.0  # minute 240, banned
    Hw[4] = 200.0  # minute 244, banned
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "remainder" and x == WIN_END


def test_stop_first_same_minute():
    # Clock minute 249 ((249+1)%5==0): close<=sl AND high>P -> stop wins.
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005, o=100.0)
    Cw[9] = 95.0  # minute 249 close below sl=96
    Hw[9] = 101.0  # same minute also touches maker
    Ow[10] = 99.0  # stop exits at open(250)
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "stop" and x == 250
    assert ret == pytest.approx(99.0 / PX - 1 - MAKER - TAKER)


def test_backstop_beats_maker():
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005, o=95.0)  # high below P1 until...
    Hw[10] = 105.0  # ...minute 250, same minute as the backstop touch
    Lw[10] = 91.0  # minute 250 low below bl=92
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "backstop" and x == 250
    assert ret == pytest.approx(92.0 / PX - 1 - MAKER - TAKER)  # min(bl, open)=92


def test_funding_on_maker_and_remainder():
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005)
    Hw[10] = 100.02
    ret_m, _, _ = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, True)
    assert ret_m == pytest.approx(P1 / PX - 1 - 2 * MAKER - FUND)
    Hw2, Lw2, Cw2, Ow2 = flat_window(h=100.005)
    ret_r, _, _ = outcome_maker_window(Hw2, Lw2, Cw2, Ow2, PX, SG, P1, 100.0, True)
    assert ret_r == pytest.approx(100.0 / PX - 1 - MAKER - TAKER - FUND)


def test_pair_non_timeout_passthrough():
    # Early TP in base -> V1 == V2 == base, extended False, no window read.
    Ha = np.full(240, 100.0)
    Ha[110] = 102.0  # f=100 => minute 110 touches TP=101
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    Hw, Lw, Cw, Ow = flat_window(h=200.0)  # would fill maker if read
    br, bx, bh, r1, x1, h1, r2, x2, h2, ext = outcome_pair_maker(
        Ha, La, Ca, Oa, 100, PX, SG, 100.0, False, Hw, Lw, Cw, Ow, 100.0)
    assert bh == "tp" and ext is False
    assert (r1, x1, h1) == (br, bx, bh) and (r2, x2, h2) == (br, bx, bh)
    assert br == pytest.approx(TP / PX - 1 - 2 * MAKER)


def test_pair_v2_split_handcheck():
    # Timeout; flat high 100.02 fills P1=100.01 half, never P3=100.03 half.
    Ha = np.full(240, 100.5)
    La = np.full(240, 99.5)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    Hw, Lw, Cw, Ow = flat_window(h=100.02, o=100.0, c=100.0, l=99.5)
    P1, P3 = 100.0 * (1 + DELTA1), 100.0 * (1 + DELTA3)
    br, bx, bh, r1, x1, h1, r2, x2, h2, ext = outcome_pair_maker(
        Ha, La, Ca, Oa, 100, PX, SG, 100.0, False, Hw, Lw, Cw, Ow, 100.0)
    assert bh == "time" and ext is True
    assert h1 == "maker"
    m1 = P1 / PX - 1 - 2 * MAKER
    rem = 100.0 / PX - 1 - MAKER - TAKER
    assert r1 == pytest.approx(m1)
    assert r2 == pytest.approx(0.5 * m1 + 0.5 * rem)
    assert h2 == "split"


def test_truncation_later_minutes_cannot_change_outcome():
    # Maker fills at minute 250; scrambling everything after must not matter.
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw, Lw, Cw, Ow = flat_window(h=100.005)
    Hw[10] = 100.02
    ref = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    Hw2 = Hw.copy()
    Hw2[11:] = 0.01  # crash after the fill
    Lw2 = Lw.copy()
    Lw2[11:] = 0.01
    got = outcome_maker_window(Hw2, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert got == ref
    # Banned-prefix scramble must not matter either.
    Hw3 = Hw.copy()
    Hw3[0:5] = 500.0
    assert outcome_maker_window(Hw3, Lw, Cw, Ow, PX, SG, P1, 100.0, False) == ref


def test_nan_window_never_triggers():
    o2, P1 = 100.0, 100.0 * (1 + DELTA1)
    Hw = np.full(60, np.nan)
    Lw = np.full(60, np.nan)
    Cw = np.full(60, np.nan)
    Ow = np.full(60, np.nan)
    ret, x, how = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, 100.0, False)
    assert how == "remainder" and x == WIN_END
    ret2, x2, how2 = outcome_maker_window(Hw, Lw, Cw, Ow, PX, SG, P1, np.nan, False)
    assert how2 == "remainder" and not np.isfinite(ret2)  # missing o3m -> drop pair


def test_results_schema_if_present():
    p = ROOT / "research/tournament/oc_makerexit/results.json"
    if not p.exists():
        pytest.skip("heavy run not done yet")
    res = json.loads(p.read_text())
    assert res["n_fills"] > 15000
    for tag in ("V1", "V2"):
        assert "dec" in res[tag] and "gate_pass" in res[tag]
        d = res[tag]["dec"]
        assert d["years_sum_ge"] <= 5 and d["years_dd_ok"] <= 5
    assert 0.0 < res["timeout_diag"]["timeout_share_base"] < 0.6
