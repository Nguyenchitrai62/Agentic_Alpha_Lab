"""Tests for oc_decayexit (IDEAS8 #6 signal-decay exit / asymmetric hold).

Pure-helper checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_decayexit.py -q
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_decayexit"))

from decayexit_rule import (B_ABS, B_REL, COOL, FRAC_V1, FRAC_V2, THETA,
                            control_mult_per_year, decay_close, decay_policy,
                            sgn_of, simulate_proxy)


def test_frac_frozen():
    assert (FRAC_V1, FRAC_V2) == (0.3, 0.5)
    assert (THETA, B_ABS, B_REL, COOL) == (0.05, 0.03, 0.40, 6)
    try:
        decay_policy(frac=0.4)
    except ValueError:
        pass
    else:
        raise AssertionError("non-frozen frac must raise")


def test_sgn_threshold_handcheck():
    assert sgn_of(0.05) == 1
    assert sgn_of(-0.05) == -1
    assert sgn_of(0.049) == 0
    assert sgn_of(-0.049) == 0
    assert sgn_of(0.0) == 0
    assert sgn_of(float("nan")) == 0


def test_decay_close_handcheck():
    # w0=0.20: V1 threshold 0.06, V2 threshold 0.10
    assert decay_close(0.05, 0.20, FRAC_V1) is True
    assert decay_close(0.059, 0.20, FRAC_V1) is True
    assert decay_close(0.06, 0.20, FRAC_V1) is False  # strict <
    assert decay_close(0.07, 0.20, FRAC_V1) is False
    assert decay_close(0.09, 0.20, FRAC_V2) is True
    assert decay_close(0.10, 0.20, FRAC_V2) is False
    assert decay_close(0.0, 0.20, FRAC_V1) is True  # signal-gone subcase
    assert decay_close(0.05, 0.0, FRAC_V1) is False  # w0<=0 never fires
    assert decay_close(float("nan"), 0.20, FRAC_V1) is False


def _flat_st(tg):
    return dict(pos=0, tg=tg, sgn=sgn_of(tg), w=0.0,
                valid=("wait", "open", "open_deep"))


def _pos_st(side, tg, w, valid=("hold", "tighten", "reduce", "close", "add"),
            since_adj=99):
    return dict(pos=side, tg=tg, sgn=sgn_of(tg), w=w, valid=valid,
                since_adj=since_adj)


def test_w0_remembered_and_decay_fires():
    pol = decay_policy(frac=FRAC_V1)
    # Flat open with tg=0.20 sets w0=0.20.
    assert pol(0, 0, _flat_st(0.20)) == "open"
    assert pol._w0[0] == 0.20
    # Same bar signal still strong: tg=0.15 (>=0.06) -> G2 hold (no decay).
    st = _pos_st(1, 0.15, 0.20)
    assert pol(1, 0, st) == "hold"
    assert pol._w0[0] == 0.20  # adds don't update w0; still entry value
    # Decayed: tg=0.05 (<0.06) -> full limit close.
    st2 = _pos_st(1, 0.05, 0.20)
    assert pol(2, 0, st2) == "close"
    # Signal-gone: tg=0.0 -> close (subcase, same as G2).
    pol2 = decay_policy(frac=FRAC_V2)
    pol2(0, 1, _flat_st(-0.30))
    assert pol2._w0[1] == 0.30
    assert pol2(1, 1, _pos_st(-1, 0.0, 0.30)) == "close"


def test_sign_flip_kept_and_winners_ride():
    pol = decay_policy(frac=FRAC_V1)
    pol(0, 0, _flat_st(0.20))
    # Reversal with strong opposite signal: tighten+close (kept), not plain close.
    st = _pos_st(1, -0.25, 0.20)
    assert pol(1, 0, st) == {"tighten": 1, "close": 1}
    # Winner rides: tg=0.19 (just below entry but above 0.06) -> not decay.
    pol2 = decay_policy(frac=FRAC_V2)
    pol2(0, 2, _flat_st(0.40))
    stw = _pos_st(1, 0.39, 0.40)
    assert pol2(1, 2, stw) == "hold"  # rides, no forced exit
    # V2 threshold 0.20: tg=0.19 fires.
    assert pol2(2, 2, _pos_st(1, 0.19, 0.40)) == "close"


def test_reversal_no_close_valid_falls_back_tighten():
    pol = decay_policy(frac=FRAC_V1)
    pol(0, 0, _flat_st(0.20))
    st = _pos_st(1, -0.25, 0.20, valid=("hold", "tighten"))
    assert pol(1, 0, st) == "tighten"


def test_proxy_handcheck_and_truncation():
    # One coin, 6 bars: enter long 0.20, hold 0.15, decay-exit at 0.05, flat, re-enter.
    ref = np.array([[0.20], [0.15], [0.05], [0.04], [0.30], [0.29]])
    px = simulate_proxy(ref, FRAC_V1)
    # Bar0 enter -> 0.20; bar1 hold (0.15>=0.06) -> 0.15; bar2 decay (0.05<0.06) -> 0;
    # bar3 flat sgn==0 (0.04<0.05) stays flat -> 0; bar4 re-enter 0.30; bar5 hold.
    assert list(px[:, 0]) == [0.20, 0.15, 0.0, 0.0, 0.30, 0.29]
    # Causality/truncation: perturbing bars >= 4 cannot change bars 0..3.
    ref2 = ref.copy()
    ref2[4:, :] = 999.0
    px2 = simulate_proxy(ref2, FRAC_V1)
    assert list(px2[:4, 0]) == list(px[:4, 0])
    # Flip case: long then strong short flips immediately; then decay-exits
    # (bar2 |-0.05| < 0.3*0.25, so the short exits to flat).
    ref3 = np.array([[0.20], [-0.25], [-0.05]])
    px3 = simulate_proxy(ref3, FRAC_V1)
    assert list(px3[:, 0]) == [0.20, -0.25, 0.0]


def test_control_mult_handcheck():
    assert control_mult_per_year(np.array([1.0, 1.0]), np.array([0.5, 0.5])) == 0.5
    assert control_mult_per_year(np.array([0.0, 0.0]), np.array([1.0])) == 1.0
    c = control_mult_per_year(np.array([2.0, 2.0]), np.array([3.0, 1.0]))
    assert abs(c - 1.0) < 1e-12
