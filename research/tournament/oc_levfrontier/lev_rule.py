"""Pure helpers for oc_levfrontier (no data access; unit-tested).

Verbatim copies:
- assign_c2: oc_chronos tilt_rule.assign_mult (C2 hi/lo 1.25/0.75, NaN -> 1.0).
- B7 constants: oc_cascadeboost boost_rule (THRESH 4.0, WINDOW 540, MIN 120,
  BOOST 1.5, B7_DAYS 7).
- stack_mult: oc_b7c2 stack_rule.stack_mult (uncapped product; non-finite -> 1.0).
- anchor_of: same convention (year y covers [ANCH5[y]+sh, min(+365d, live1))).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

C2_HI = 1.25
C2_LO = 0.75
B7_BOOST = 1.5
B7_DAYS = 7
THRESH = 4.0
WINDOW = 540
MIN_PERIODS = 120


def assign_c2(risk: float, direction: int, q20: float, q80: float,
              hi: float = C2_HI, lo: float = C2_LO) -> float:
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:
        return lo
    if r <= q20:
        return hi
    return 1.0


def stack_mult(m_b7: float, m_c2: float) -> float:
    a = float(m_b7) if m_b7 is not None and np.isfinite(float(m_b7)) else 1.0
    b = float(m_c2) if m_c2 is not None and np.isfinite(float(m_c2)) else 1.0
    return a * b


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
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
