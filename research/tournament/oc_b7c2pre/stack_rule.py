"""Pure stack-rule helpers for oc_b7c2pre (no data access; unit-tested).

B7C2 stack on the pre-sample replica (pre-registered, verbatim oc_b7c2 arithmetic):
dip sizing multiplier = m_B7 * m_C2, where
  m_B7 in {1.0, 1.5} = dip budget boost for 7 days after a >4sg 4h move
    (market-wide per shift; frozen boost_mult_presample.parquet from oc_cboostpre),
  m_C2 in {0.75, 1.0, 1.25} = Chronos downside-quantile tilt on outer quintiles
    of risk = -ch_q10 (frozen anchor-2021 fit from oc_presampletilt, applied to all
    pre-sample years and labelled "fit from later data, rule frozen").
B7C2_cap: m = min(m_B7 * m_C2, 1.5).

assign_c2 is a verbatim copy of oc_b7c2 stack_rule.assign_c2 /
oc_presampletilt tilt_rule.assign_mult (C2: hi/lo 1.25/0.75, direction +1).
"""

from __future__ import annotations

import numpy as np

# Frozen anchor-2021 C2 fit (verbatim oc_presampletilt FROZEN_2021["C2"]).
C2_DIRECTION = 1
C2_Q20 = 1.110054237503456
C2_Q80 = 2.8608138206510407

C2_HI = 1.25
C2_LO = 0.75
B7_BOOST = 1.5
STACK_CAP = 1.5


def assign_c2(risk: float, direction: int = C2_DIRECTION,
              q20: float = C2_Q20, q80: float = C2_Q80,
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


def variant_mult_c2(risk: float) -> float:
    """C2 multiplier with the frozen anchor-2021 fit."""
    return assign_c2(risk, C2_DIRECTION, C2_Q20, C2_Q80, C2_HI, C2_LO)


def stack_mult(m_b7: float, m_c2: float) -> float:
    """Pre-registered B7C2 product; non-finite leg counts as 1.0."""
    a = float(m_b7) if m_b7 is not None and np.isfinite(float(m_b7)) else 1.0
    b = float(m_c2) if m_c2 is not None and np.isfinite(float(m_c2)) else 1.0
    return a * b


def stack_mult_cap(m_b7: float, m_c2: float, cap: float = STACK_CAP) -> float:
    """Pre-registered B7C2_cap: product clipped to <= cap."""
    return min(stack_mult(m_b7, m_c2), float(cap))
