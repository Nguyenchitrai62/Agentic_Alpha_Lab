"""oc_fundhold pure helpers (no data access; unit-tested).

Settled-funding condition (frozen PLAN.md):
  F(T_out, sym) = last settled last_funding_rate with calc_time STRICTLY before
  the base timeout open T_out = T+240. Thresholds q70/q50 per anchor-coin over
  settlements in [A-97d, A-7d), >= 50 else NaN (never extend). Expensive iff
  finite F and finite q and F > q (strict); NaN -> exit on time (no extension).
"""
from __future__ import annotations

import numpy as np

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
MIN_POOL = 50


def last_settled_before(settle_ns: np.ndarray, settle_rate: np.ndarray,
                        t_out_ns: np.ndarray) -> np.ndarray:
    """Last settled rate with calc_time strictly before each timeout open.

    settle_ns: settlement calc_time ns (sorted ascending). settle_rate: matching
    rates. t_out_ns: timeout-open ns array. Returns NaN where no prior settlement.
    """
    settle_ns = np.asarray(settle_ns, dtype=np.int64)
    settle_rate = np.asarray(settle_rate, dtype=float)
    t_out_ns = np.asarray(t_out_ns, dtype=np.int64)
    pos = np.searchsorted(settle_ns, t_out_ns, side="left") - 1
    out = np.full(len(t_out_ns), np.nan)
    ok = pos >= 0
    out[ok] = settle_rate[np.clip(pos[ok], 0, len(settle_rate) - 1)]
    return out


def anchor_of(t_ns: np.ndarray, anch_ns: np.ndarray) -> np.ndarray:
    """Year index per timestamp (clip to [0,4])."""
    return np.clip(np.searchsorted(anch_ns, t_ns, side="right") - 1, 0, 4)


def quantile_pool(pool: np.ndarray, q: float) -> float:
    """q-th quantile (0..1) over finite pool values, else NaN. Never imputes."""
    pool = np.asarray(pool, dtype=float)
    pool = pool[np.isfinite(pool)]
    if len(pool) < MIN_POOL:
        return float("nan")
    return float(np.quantile(pool, q))


def expensive_flag(F: np.ndarray, q: float) -> np.ndarray:
    """True iff finite F and finite q and F > q (strict). NaN -> False (exit)."""
    F = np.asarray(F, dtype=float)
    if not np.isfinite(q):
        return np.zeros(len(F), dtype=bool)
    return np.isfinite(F) & (F > q)


def should_extend(F: float, q: float) -> bool:
    """Scalar version: extend iff cheap (finite F <= finite q).

    Returns True (extend +8h) only when F and q are both finite and F <= q.
    Expensive (F > q) -> False (exit on time); NaN F or NaN q -> False (exit on
    time, never extend on missing data, never imputed).
    """
    if not (np.isfinite(F) and np.isfinite(q)):
        return False
    return not bool(F > q)
