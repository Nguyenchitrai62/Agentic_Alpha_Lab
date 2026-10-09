"""Pure tilt-rule helpers for oc_d1c2 (no data access; unit-tested).

Legs (frozen fits from the source studies, hi/lo 1.25/0.75):
  m_D1 = assign_mult(risk_D1, fits_D1[A].direction/q20/q80); NaN -> 1.0.
  m_C2 = assign_mult(-ch_q10, fits_C2[A].direction/q20/q80); NaN -> 1.0.
Ensembles (frozen PLAN.md):
  AVG   = (m_D1 + m_C2) / 2  (missing leg already 1.0 via assign_mult).
  AGREE = 1.25 iff both 1.25, 0.75 iff both 0.75, else 1.0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

HI = 1.25
LO = 0.75


def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float = HI, lo: float = LO) -> float:
    """Final multiplier for one (coin, holding bar); NaN risk -> 1.0."""
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


def ensemble_avg(m_d1: float | None, m_c2: float | None) -> float:
    """Pre-registered AVG: mean of the two leg multipliers; missing leg = 1.0."""
    a = float(m_d1) if m_d1 is not None and np.isfinite(float(m_d1)) else 1.0
    b = float(m_c2) if m_c2 is not None and np.isfinite(float(m_c2)) else 1.0
    return (a + b) / 2.0


def ensemble_agree(m_d1: float | None, m_c2: float | None) -> float:
    """Pre-registered AGREE: 1.25 iff both 1.25, 0.75 iff both 0.75, else 1.0."""
    a = float(m_d1) if m_d1 is not None and np.isfinite(float(m_d1)) else 1.0
    b = float(m_c2) if m_c2 is not None and np.isfinite(float(m_c2)) else 1.0
    if a == HI and b == HI:
        return HI
    if a == LO and b == LO:
        return LO
    return 1.0


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention as
    oc_chronos/oc_downshare: year y covers [ANCH5[y]+sh, min(+365d, live1)))."""
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
