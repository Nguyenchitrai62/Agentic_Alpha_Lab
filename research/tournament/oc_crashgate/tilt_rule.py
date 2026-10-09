"""Pure tilt-rule helpers for oc_crashgate (no data access; unit-tested).

Base rule (identical to C2): per anchor A, direction = sign of
Spearman(risk, y_dep), edges q20/q80 of risk. Multiplier hi in the favourable
outer quintile, lo in the unfavourable outer quintile, 1 otherwise;
missing/NaN risk -> 1. C2: hi/lo = 1.25/0.75.
Crash gate (IDEAS5 #1, frozen thresholds, no fit): V1 X = 0.15, V2 X = 0.10.
  gated = m_base if depth(T) < X else 1.0,
where depth(T) = max intra-window peak-to-trough of BTC 4h closes with
close_time in (T - 30d, T] (floored at 0). NaN depth (insufficient history)
-> allow (base mult; inert in our years).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

V1_X = 0.15
V2_X = 0.10


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


def depth_of_window(closes) -> float:
    """Max peak-to-trough depth over closes in time order (floored at 0).

    closes: 1D array-like of positive prices, oldest first. Returns NaN when
    fewer than 2 finite closes are available. Pure function (no timestamps).
    """
    p = np.asarray(list(closes), dtype=float)
    p = p[np.isfinite(p)]
    if p.size < 2:
        return float("nan")
    peak = p[0]
    best = 0.0
    for v in p[1:]:
        if v > peak:
            peak = v
        elif peak > 0 and np.isfinite(peak):
            dd = (peak - v) / peak
            if dd > best:
                best = dd
    return float(best)


def gate_mult(m_base: float, depth: float, x: float) -> float:
    """Crash gate: tilt applies only when trailing-30d depth < X."""
    m = float(m_base)
    if not np.isfinite(m):
        return 1.0
    d = float(depth)
    if not np.isfinite(d):
        return m  # insufficient history -> allow (inert in our years)
    return m if d < float(x) else 1.0


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
