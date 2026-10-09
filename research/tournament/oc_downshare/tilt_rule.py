"""Pure tilt-rule helpers for oc_downshare (no data access; unit-tested).

D1/D2 rule (identical K2/C2 quintile form except the risk): per anchor A, on
harness training majors rows (t_exit < A - 7d, shift-0 feature present):
direction = +1 if Spearman(risk, y_dep) > 0 else -1; edges q20/q80 of risk.
Multiplier hi in the favourable outer quintile, lo in the unfavourable outer
quintile, 1 otherwise; missing/NaN risk -> 1. Both variants: hi/lo = 1.25/0.75.

Risk definitions (frozen PLAN.md):
  share(rs) = sum(min(r,0)^2) / sum(r^2); NaN unless all finite and total > 0.
  D1[E] = share(r[E-36 .. E-1]) (trailing 6d = 36 4h returns).
  D2[E] = 0.6 * share(r[E-6 .. E-1]) + 0.4 * share(r[E-30 .. E-1]) (HAR-RS blend).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

W_DAILY = 0.6
W_WEEKLY = 0.4
WIN_D1 = 36
WIN_DAILY = 6
WIN_WEEKLY = 30


def share_of(rs) -> float:
    """Downside-RV share of a return window (pure function)."""
    a = np.asarray(list(rs), dtype=float)
    if a.size == 0:
        return float("nan")
    if not np.all(np.isfinite(a)):
        return float("nan")
    total = float(np.sum(a * a))
    if not np.isfinite(total) or total <= 0:
        return float("nan")
    down = float(np.sum(np.minimum(a, 0.0) ** 2))
    return float(down / total)


def blend_d2(share_daily: float, share_weekly: float) -> float:
    """HAR-RS frozen blend 0.6/0.4; NaN if either leg NaN."""
    d, w = float(share_daily), float(share_weekly)
    if not (np.isfinite(d) and np.isfinite(w)):
        return float("nan")
    return float(W_DAILY * d + W_WEEKLY * w)


def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float, lo: float) -> float:
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


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention as
    oc_kronosmanual: year y covers [ANCH5[y]+sh, min(+365d, live1)))."""
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
