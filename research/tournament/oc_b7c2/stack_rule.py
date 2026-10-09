"""Pure stack-rule helpers for oc_b7c2 (no data access; unit-tested).

B7C2 stack (pre-registered): dip rung size multiplier = m_B7 * m_C2, where
  m_B7 in {1.0, 1.5} = dip budget boost for 7 days after a >4sg 4h move
    (market-wide per shift; frozen boost_mult_4shift.parquet from oc_cascadeboost),
  m_C2 in {0.75, 1.0, 1.25} = Chronos downside-quantile tilt on outer quintiles
    of risk = -ch_q10 (per-anchor fits from oc_chronos fits.json).
B7C2_cap: m = min(m_B7 * m_C2, 1.5).

assign_c2 is a verbatim copy of oc_chronos tilt_rule.assign_mult (C2: hi/lo 1.25/0.75).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

C2_HI = 1.25
C2_LO = 0.75
B7_BOOST = 1.5
STACK_CAP = 1.5


def assign_c2(risk: float, direction: int, q20: float, q80: float,
              hi: float = C2_HI, lo: float = C2_LO) -> float:
    """Final C2 leg multiplier for one (coin, holding bar); NaN risk -> 1.0."""
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:  # high risk favourable
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:  # high risk unfavourable
        return lo
    if r <= q20:
        return hi
    return 1.0


def stack_mult(m_b7: float, m_c2: float) -> float:
    """Pre-registered B7C2 product; non-finite leg counts as 1.0."""
    a = float(m_b7) if m_b7 is not None and np.isfinite(float(m_b7)) else 1.0
    b = float(m_c2) if m_c2 is not None and np.isfinite(float(m_c2)) else 1.0
    return a * b


def stack_mult_cap(m_b7: float, m_c2: float, cap: float = STACK_CAP) -> float:
    """Pre-registered B7C2_cap: product clipped to <= cap."""
    return min(stack_mult(m_b7, m_c2), float(cap))


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention as
    oc_chronos/oc_cascadeboost: year y covers [ANCH5[y]+sh, min(+365d, live1)))."""
    sh = pd.Timedelta(hours=shift)
    live1 = pd.Timestamp(y1, tz="UTC") + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC") + sh:
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return 4
