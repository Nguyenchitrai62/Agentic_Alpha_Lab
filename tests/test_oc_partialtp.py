"""Tests for oc_partialtp (IDEAS6 #2 stop-funded partial TP).

Pure-numpy core checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_partialtp.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_partialtp"))

from partialtp import (FUND, MAKER, MU_V1, MU_V2, TAKER, find_fill, n_vector,
                       outcome_mu, outcome_pair_partial, outcome_partial)

PX = 100.0
SG = 0.01
SL = PX * (1 - 4 * SG)  # 96
BL = PX * (1 - 8 * SG)  # 92
PP1 = PX * (1 + MU_V1 * SG)  # 100.5
PP2 = PX * (1 + MU_V2 * SG)  # 100.75
TP = PX * (1 + 1.0 * SG)  # 101


def flat_bars(h=100.0, l=99.5, c=100.0, o=100.0):
    return (np.full(240, h), np.full(240, l), np.full(240, c), np.full(240, o))


def test_find_fill_strict():
    assert find_fill(np.array([100.0, 100.0, 99.9]), 100.0) == 2
    assert find_fill(np.array([100.0, 100.0]), 100.0) is None  # == never fills
    assert find_fill(np.array([np.nan, 99.0]), 100.0) == 1  # NaN never fills


def test_n_vector_nan_safe():
    close = np.array([[np.nan, 90.0]])
    assert list(n_vector(close, np.array([100.0]), np.array([0.01]))) == [0, 1]


def test_base_timeout_handcheck():
    # Flat market at px: no TP, no stop, no backstop -> timeout at o2 taker.
    Ha, La, Ca, Oa = flat_bars(h=100.5, l=99.5)
    ret, x, how = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 100.0, False)
    assert how == "time" and x == 240
    assert ret == pytest.approx(100.0 / PX - 1 - MAKER - TAKER)


def test_no_partial_touch_equals_base():
    # High never reaches Pp=100.5 -> V1 == V2 == BASE exactly.
    Ha, La, Ca, Oa = flat_bars(h=100.4, l=99.5)
    br, bx, bh, r1, x1, h1, r2, x2, h2, split = outcome_pair_partial(
        Ha, La, Ca, Oa, 100, PX, SG, 100.0, False)
    assert split is False
    assert (r1, x1, h1) == (br, bx, bh) and (r2, x2, h2) == (br, bx, bh)
    assert bh == "time"


def test_partial_then_runner_both_tp_handcheck():
    # Partial at minute 110 (high 100.6 > 100.5), runner TP at 120 (high 101.1).
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 100.6
    Ha[120] = 101.5
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "part_tp" and x == 120
    r_part = PP1 / PX - 1 - 2 * MAKER
    r_rem = TP / PX - 1 - 2 * MAKER
    assert ret == pytest.approx(0.5 * r_part + 0.5 * r_rem)


def test_partial_same_minute_as_runner():
    # High jumps straight through tp: both halves fill maker the same minute.
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 102.0
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "part_tp" and x == 110
    r_part = PP1 / PX - 1 - 2 * MAKER
    r_rem = TP / PX - 1 - 2 * MAKER
    assert ret == pytest.approx(0.5 * r_part + 0.5 * r_rem)


def test_stop_first_same_minute_as_partial():
    # Clock minute 109 ((109+1)%5==0): close<=sl AND high>Pp -> whole stop wins.
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=99.0)
    Ca[109] = 95.0
    Ha[109] = 101.0
    Oa[110] = 98.0
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "stop" and x == 110
    assert ret == pytest.approx(98.0 / PX - 1 - MAKER - TAKER)


def test_backstop_beats_partial_same_minute():
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=95.0)
    Ha[110] = 102.0
    La[110] = 91.0
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "backstop" and x == 110
    assert ret == pytest.approx(92.0 / PX - 1 - MAKER - TAKER)


def test_partial_then_stop_handcheck():
    # Partial at 110, close5 stop signal at 114 -> remainder exits at open(115).
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 100.6
    Ca[114] = 95.0  # (114+1)%5==0 -> signal
    Oa[115] = 97.0
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "part_stop" and x == 115
    r_part = PP1 / PX - 1 - 2 * MAKER
    r_rem = 97.0 / PX - 1 - MAKER - TAKER
    assert ret == pytest.approx(0.5 * r_part + 0.5 * r_rem)


def test_partial_then_timeout_pays_half_funding():
    # Partial at 110, flat after -> remainder times out at o2 with settle.
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 100.6
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 99.0, True)
    assert how == "part_time" and x == 240
    r_part = PP1 / PX - 1 - 2 * MAKER
    r_rem = 99.0 / PX - 1 - MAKER - TAKER - FUND
    assert ret == pytest.approx(0.5 * r_part + 0.5 * r_rem)
    # Base whole timeout pays the FULL funding drag: partial saves half the fund
    # and banks half at Pp, so it must beat the timed-out base here.
    br, _, _ = outcome_mu(Ha, La, Ca, Oa, 100, PX, SG, 1.0, 99.0, True)
    assert ret > br


def test_v1_v2_differ_only_by_partial_level():
    # High 100.6 touches V1 (100.5) but not V2 (100.75); runner never hit.
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 100.6
    br, bx, bh, r1, x1, h1, r2, x2, h2, split = outcome_pair_partial(
        Ha, La, Ca, Oa, 100, PX, SG, 100.0, False)
    assert h1.startswith("part_") and not h2.startswith("part_")
    assert (r2, x2, h2) == (br, bx, bh)
    assert split is True


def test_truncation_later_minutes_cannot_change_outcome():
    # Partial+runner done by minute 120; scrambling after must not matter.
    Ha, La, Ca, Oa = flat_bars(h=100.0, l=99.5, c=100.0, o=100.0)
    Ha[110] = 100.6
    Ha[120] = 101.5
    ref = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    Ha2 = Ha.copy()
    Ha2[121:] = 0.01
    La2 = La.copy()
    La2[121:] = 0.01
    assert outcome_partial(Ha2, La2, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False) == ref
    # Scrambling pre-fill minutes must not matter either.
    Ha3 = Ha.copy()
    Ha3[:100] = 500.0
    assert outcome_partial(Ha3, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False) == ref


def test_nan_never_triggers():
    Ha = np.full(240, np.nan)
    La = np.full(240, np.nan)
    Ca = np.full(240, np.nan)
    Oa = np.full(240, np.nan)
    ret, x, how = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, 100.0, False)
    assert how == "time" and x == 240  # no touch anywhere -> timeout
    ret2, _, how2 = outcome_partial(Ha, La, Ca, Oa, 100, PX, SG, MU_V1, np.nan, False)
    assert how2 == "time" and not np.isfinite(ret2)  # missing o2 -> drop pair


def test_results_schema_if_present():
    p = ROOT / "research/tournament/oc_partialtp/results.json"
    if not p.exists():
        pytest.skip("heavy run not done yet")
    res = json.loads(p.read_text())
    assert res["n_fills"] > 15000
    for tag in ("V1", "V2"):
        assert "dec" in res[tag] and "gate_pass" in res[tag]
        d = res[tag]["dec"]
        assert d["years_sum_ge"] <= 5 and d["years_dd_ok"] <= 5
    assert 0.0 < res["partial_diag"]["split_share_V1"] < 1.0
