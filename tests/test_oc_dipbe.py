"""oc_dipbe tests: BE trigger/stop mechanics on synthetic paths (+ causality)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_dipbe"
sys.path.insert(0, str(OC))
import be_core as B

MK, TK = 0.0002, 0.00055


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    L = np.full(n, o)
    C = np.full(n, o)
    return O, H, L, C


def test_parity_when_never_triggered():
    # flat path: no BE trigger, no base touch -> both timeout identically
    sg, f, px, o2 = 0.01, 20, 98.0, 98.1
    O, H, L, C = _flat(o=px)
    r0, x0, h0 = B.outcome_base(H, L, C, O, f, px, sg, o2, False)
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, o2, False)
    assert not armed and (h0, h1) == ("time", "time")
    assert (r0, x0) == (r1, x1)


def test_trigger_strict_boundary():
    # high == be_trig exactly does NOT arm (STRICT, same as TP convention)
    sg, f, px = 0.01, 20, 98.0
    be = px * (1 + 0.6 * sg)
    O, H, L, C = _flat(o=px)
    H[30] = be  # exactly at the level
    _, _, _, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert not armed
    H[30] = be + 1e-9
    _, _, _, armed2 = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert armed2


def test_same_minute_tp_tie_goes_to_base():
    # high exceeds be_trig and tp in the SAME minute -> TP wins, no BE arm
    sg, f, px = 0.01, 20, 98.0
    tp = px * (1 + sg)
    O, H, L, C = _flat(o=px)
    H[30] = tp + 0.01  # also > be_trig (0.6sg < 1.0sg)
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert not armed and h1 == "tp" and x1 == 30
    assert abs(r1 - (tp / px - 1 - 2 * MK)) < 1e-12


def test_be_stop_exit_nets_zero_at_level():
    # trigger BE, then close below be_stop at a clock minute -> stop at next
    # open; exit exactly at be_stop nets 0 (be/px-1 == MK+TK)
    sg, f, px = 0.01, 20, 98.0
    be = px * (1 + MK + TK)
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.6 * sg) + 0.01  # arm at tb=30
    assert (30 + 1) % 5 != 0  # trigger minute is not a clock minute here
    m = 34  # (34+1)%5==0 clock minute
    assert (m + 1) % 5 == 0
    C[m] = be - 0.01
    O[m + 1] = be
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert armed and h1 == "stop" and x1 == m + 1
    assert abs(r1) < 1e-12


def test_be_stop_level_is_fill_plus_fees():
    sg, px = 0.01, 98.0
    assert abs(px * (1 + MK + TK) - px * 1.00075) < 1e-12
    assert sg > 0  # trigger (0.6sg) sits strictly below TP (1.0sg)


def test_backstop_before_trigger_keeps_priority():
    # backstop hit before any BE trigger -> base backstop, no arm
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    L[25] = px * (1 - 8 * sg) - 0.01
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert not armed and h1 == "backstop" and x1 == 25


def test_base_stop_before_trigger_no_arm():
    # base close-stop fires before BE trigger minute -> no arm, base stop
    sg, f, px = 0.01, 20, 98.0
    sl = px * (1 - 4 * sg)
    O, H, L, C = _flat(o=px)
    m = 24  # clock minute
    assert (m + 1) % 5 == 0
    C[m] = sl - 0.01
    H[60] = px * (1 + 0.6 * sg) + 0.01  # would-be trigger comes later
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert not armed and h1 == "stop"


def test_trigger_minute_uses_sl_not_be():
    # close at the trigger minute tb below be_stop but above sl does NOT stop
    # at tb (m>tb only); timeout follows
    sg, f, px = 0.01, 20, 98.0
    sl = px * (1 - 4 * sg)
    be = px * (1 + MK + TK)
    O, H, L, C = _flat(o=px)
    C[:] = be + 0.01  # flat closes stay above be_stop (else every clock stops)
    tb = 29
    H[tb] = px * (1 + 0.6 * sg) + 0.01
    C[tb] = (sl + be) / 2  # below be_stop, above sl
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    assert armed and (h1, x1) == ("time", 240)


def test_causality_future_blind():
    # truncating all minutes after the BE-stop exit leaves the outcome unchanged
    sg, f, px = 0.01, 20, 98.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.6 * sg) + 0.01
    m = 34
    C[m] = px * (1 + MK + TK) - 0.01
    O[m + 1] = px * (1 + MK + TK)
    H[100], L[100], C[100] = px * 2, px * 0.5, px * 0.5  # far-future noise
    r1, x1, h1, _ = B.outcome_be(H, L, C, O, f, px, sg, 99.0, False)
    H2, L2, C2, O2 = (a[:60].copy() for a in (H, L, C, O))
    H2 = np.concatenate([H2, np.full(240 - 60, np.nan)])
    L2 = np.concatenate([L2, np.full(240 - 60, np.nan)])
    C2 = np.concatenate([C2, np.full(240 - 60, np.nan)])
    O2 = np.concatenate([O2, np.full(240 - 60, np.nan)])
    r2, x2, h2, _ = B.outcome_be(H2, L2, C2, O2, f, px, sg, 99.0, False)
    assert (h1, x1) == (h2, x2) == ("stop", m + 1)
    assert abs(r1 - r2) < 1e-12


def test_be_timeout_after_arming_keeps_funding():
    # armed but never stopped/TP'd -> timeout with settle funding, flagged armed
    sg, f, px, o2 = 0.01, 20, 98.0, 98.0
    O, H, L, C = _flat(o=px)
    H[30] = px * (1 + 0.6 * sg) + 0.01
    C[:] = px * (1 + MK + TK) + 0.01  # closes stay above be_stop
    H[31:] = px  # no TP touch after arming
    r1, x1, h1, armed = B.outcome_be(H, L, C, O, f, px, sg, o2, True)
    assert armed and (h1, x1) == ("time", 240)
    assert abs(r1 - (o2 / px - 1 - MK - TK - 0.0001)) < 1e-12
