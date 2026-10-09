"""Pure OI-short-cover-gate helpers for oc_oishort (no data access; unit-tested).

Frozen rule (PLAN.md): per 4h close T and coin,
  dOI(T) = ln(OI_now / OI_24h)  (OI as-of <= T-5min / <= T-24h-5min),
  R24(T) = ln(C4(T) / C4(T-24h)) (hourly closes with END <= T),
  sg(T)  = std of the 360 single-step log returns strictly before T
           (rets[t-360:t], >=120 finite, sd > 0 else NaN),
  z = (dOI - mu[A]) / sd[A] with mu/sd over [A-372d, A-7d) per anchor,
  gate_O1 = z > 2.0 AND R24 < -2*sg; gate_O2 = z > 1.5 AND same price leg.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
Z_O1 = 2.0
Z_O2 = 1.5
PRICE_K = 2.0
SG_WIN = 360
SG_MIN = 120
EMBARGO_D = 7
NORM_DAYS = 365
MIN_NORM = 1000


def log_change(now: float, prev: float) -> float:
    """ln(now/prev); NaN if missing/non-positive/non-finite."""
    try:
        a = float(now)
        b = float(prev)
    except (TypeError, ValueError):
        return float("nan")
    if not (math.isfinite(a) and math.isfinite(b)) or a <= 0 or b <= 0:
        return float("nan")
    return float(math.log(a / b))


def trailing_sg(rets_before: np.ndarray, win: int = SG_WIN,
                min_obs: int = SG_MIN) -> float:
    """Std of single-step log returns strictly before T (causal, shifted).

    rets_before: 1-D array of returns ending at T-4h and earlier (oldest first).
    Uses the last `win` values; NaN unless >= min_obs finite and sd > 0.
    """
    r = np.asarray(rets_before, dtype=np.float64).ravel()
    if r.size == 0:
        return float("nan")
    tail = r[-win:]
    tail = tail[np.isfinite(tail)]
    if tail.size < min_obs:
        return float("nan")
    sd = float(np.std(tail, ddof=1))
    if not math.isfinite(sd) or sd <= 0:
        return float("nan")
    return sd


def price_trigger(r24: float, sg: float, k: float = PRICE_K) -> bool:
    """R24 < -k*sg (strictly). NaN / sg<=0 -> False (never gate)."""
    try:
        r = float(r24)
        s = float(sg)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(r) and math.isfinite(s)) or s <= 0:
        return False
    return bool(r < -float(k) * s)


def gate_short(doi: float, mu: float, sd: float, r24: float, sg: float,
               z_thr: float = Z_O1) -> bool:
    """Full short-cover gate: z > thr AND price_trigger. NaN-safe -> False."""
    try:
        v = float(doi)
        m = float(mu)
        e = float(sd)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and math.isfinite(m) and math.isfinite(e)) or e <= 1e-12:
        return False
    if not ((v - m) / e > float(z_thr)):
        return False
    return price_trigger(r24, sg)


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
