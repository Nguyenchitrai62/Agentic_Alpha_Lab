"""Pure VPIN-gate helpers for oc_vpinveto (no data access; unit-tested).

Frozen rule (PLAN.md): per 4h close T and coin, VPIN over trailing 24h of 1m bars
split chronologically into 50 equal-volume buckets:
  VPIN = sum_b |sum(B-S) in b| / sum_b V_b,  V = B+S (quote notional).
Norms per anchor A (pre-anchor + 7d embargo): mu/sd over VPIN(T) for
T in [A-372d, A-7d]; z = (VPIN-mu)/sd; gate = z > 2.0.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-23")
# NOTE: engine Y1 is 2026-09-23; last anchor year is [2025-09-24, 2026-09-23).
N_BUCKETS = 50
WIN_H = 24
Z_THR = 2.0
EMBARGO_D = 7
NORM_DAYS = 365


def bvc_buy_frac(dclose: float, sigma: float) -> float:
    """Normal-CDF bulk-volume-classification buy fraction (synthetic-test helper).

    Phi(dclose / sigma); sigma<=0 or non-finite -> 0.5 (neutral, disclosed).
    NOT used on real data (real data uses exchange taker flags).
    """
    try:
        x = float(dclose)
        s = float(sigma)
    except (TypeError, ValueError):
        return 0.5
    if not (math.isfinite(x) and math.isfinite(s)) or s <= 0:
        return 0.5
    return 0.5 * (1.0 + math.erf(x / (s * math.sqrt(2.0))))


def bucketed_vpin(buy: np.ndarray, sell: np.ndarray, n_buckets: int = N_BUCKETS) -> float:
    """VPIN-50 form over one trailing window (chronological equal-volume buckets).

    buy/sell: per-1m notional arrays (same length, time order). Returns NaN when
    the window is unusable (total volume <= 0).
    """
    b = np.asarray(buy, dtype=np.float64).ravel()
    s = np.asarray(sell, dtype=np.float64).ravel()
    if b.shape != s.shape or b.size == 0:
        return float("nan")
    v = b + s
    total = float(np.sum(v))
    if not math.isfinite(total) or total <= 0:
        return float("nan")
    d = b - s
    # cumulative-volume bucket edges (equal total/ n_buckets per bucket)
    target = total / float(n_buckets)
    cum = np.cumsum(v)
    imb_sum = 0.0
    start = 0
    edge = target
    n = b.size
    for i in range(n):
        if cum[i] >= edge or i == n - 1:
            seg = d[start:i + 1].sum()
            imb_sum += abs(float(seg))
            start = i + 1
            edge += target
            if start >= n:
                break
    # any leftover (rounding) goes to a final bucket
    if start < n:
        imb_sum += abs(float(d[start:].sum()))
    return float(imb_sum / total)


def gate_z(vpin: float, mu: float, sd: float, thr: float = Z_THR) -> bool:
    """z = (vpin-mu)/sd; gate iff z > thr. NaN / sd<=0 -> False (never gate)."""
    try:
        v, m, e = float(vpin), float(mu), float(sd)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and math.isfinite(m) and math.isfinite(e)) or e <= 1e-12:
        return False
    return bool((v - m) / e > float(thr))


def anchor_of(t, shifts_note: str = "") -> int:
    """Year index 0..4 of 4h close T (standard grid, no shift).

    Year y covers [ANCH5[y], ANCH5[y]+365d) except y=4 which ends 2026-09-23.
    T < first anchor -> 0 (unused; rows before 2021-09-24 are never gated).
    """
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC"):
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        if y == 4:
            a1 = min(a1, pd.Timestamp("2026-09-23", tz="UTC") + pd.Timedelta(days=1))
        if a0 <= tt < a1:
            return y
    return 4
