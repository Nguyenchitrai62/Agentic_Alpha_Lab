"""Pure LS-ratio contrarian-gate helpers for oc_lsratio (no data access; unit-tested).

Frozen rule (PLAN.md): per 4h close T and coin,
  LS(T) = last count_toptrader_long_short_ratio with create_time <= T-5min,
  p90[A]/p10[A] over LS(T) for T in [A-372d, A-7d) per anchor (pre-anchor + 7d
  embargo, >=1000 finite samples else NaN),
  gate_long  = LS > p90 (strictly); gate_short = LS < p10 (strictly).
L1: longs x0.5 on gate_long. L2: L1 + shorts x0.5 on gate_short.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
P_HI = 90.0
P_LO = 10.0
EMBARGO_D = 7
NORM_DAYS = 365
MIN_NORM = 1000


def asof_ratio(metric_times_ns: np.ndarray, metric_vals: np.ndarray,
               query_ns: np.ndarray) -> np.ndarray:
    """Last metric value with time <= query (causal asof, no imputation).

    Non-finite / non-positive values propagate as NaN at query time (gate-off).
    metric_times_ns must be sorted ascending.
    """
    mt = np.asarray(metric_times_ns, dtype=np.int64).ravel()
    mv = np.asarray(metric_vals, dtype=np.float64).ravel()
    q = np.asarray(query_ns, dtype=np.int64).ravel()
    pos = np.searchsorted(mt, q, side="right") - 1
    out = np.full(len(q), np.nan)
    ok = pos >= 0
    take = mv[np.clip(pos[ok], 0, len(mv) - 1)]
    take = np.where(np.isfinite(take) & (take > 0), take, np.nan)
    out[ok] = take
    return out


def gate_long(ls: float, p90: float) -> bool:
    """LS > p90 (strictly). NaN / non-positive -> False (never gate)."""
    try:
        v = float(ls)
        p = float(p90)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and math.isfinite(p)) or v <= 0 or p <= 0:
        return False
    return bool(v > p)


def gate_short(ls: float, p10: float) -> bool:
    """LS < p10 (strictly). NaN / non-positive -> False (never gate)."""
    try:
        v = float(ls)
        p = float(p10)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and math.isfinite(p)) or v <= 0 or p <= 0:
        return False
    return bool(v < p)


def anchor_of(t, anchors=ANCH5) -> int:
    """Year index 0..4 of 4h close T (standard grid, no shift).

    Year y covers [ANCH[y], ANCH[y]+365d). T < first anchor -> 0
    (unused; rows before 2021-09-24 are never gated).
    """
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(anchors[0], tz="UTC"):
        return 0
    for y, a in enumerate(anchors):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        if a0 <= tt < a1:
            return y
    return len(anchors) - 1
