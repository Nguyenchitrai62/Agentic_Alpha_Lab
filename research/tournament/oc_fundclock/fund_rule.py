"""oc_fundclock pure helpers (no data access; unit-tested).

Predicted proxy P(S): 60m premium TWAP ending 1h before settlement.
Thresholds: per-anchor-coin q90 over [A-97d, A-7d).
Flag: P(S) > q90 (strict).
"""
from __future__ import annotations

import numpy as np

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
MIN_BARS = 30
MIN_POOL = 50


def premium_twap_before(prem_ns: np.ndarray, prem_close: np.ndarray,
                        s_floor_ns: np.ndarray) -> np.ndarray:
    """Mean premium close over bars with open in [Sf-120m, Sf-60m).

    prem_ns: premium bar open_time ns (sorted ascending).
    s_floor_ns: settlement-floor ns array.
    Returns NaN where < MIN_BARS valid bars.
    """
    w0 = np.int64(120 * 60 * 10**9)
    w1 = np.int64(60 * 60 * 10**9)
    out = np.full(len(s_floor_ns), np.nan)
    # cumsum for fast means (nan-safe via mask)
    vals = prem_close.astype(float)
    finite = np.isfinite(vals)
    v = np.where(finite, vals, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(v)])
    cn = np.concatenate([[0], np.cumsum(finite.astype(np.int64))])
    lo = np.searchsorted(prem_ns, s_floor_ns - w0, side="left")
    hi = np.searchsorted(prem_ns, s_floor_ns - w1, side="left")
    # hi is first idx with open >= Sf-61m; window = [lo, hi)
    n = hi - lo
    sums = cs[hi] - cs[lo]
    cnt = cn[hi] - cn[lo]
    ok = (n >= MIN_BARS) & (cnt >= MIN_BARS)
    out[ok] = sums[ok] / cnt[ok]
    return out


def gate_flag(pred: np.ndarray, q90: float) -> np.ndarray:
    """Flagged iff finite pred and finite q90 and pred > q90."""
    pred = np.asarray(pred, dtype=float)
    if not np.isfinite(q90):
        return np.zeros(len(pred), dtype=bool)
    return np.isfinite(pred) & (pred > q90)


def anchor_of(t_ns: np.ndarray, anch_ns: np.ndarray) -> np.ndarray:
    """Year index per timestamp (clip to [0,4])."""
    return np.clip(np.searchsorted(anch_ns, t_ns, side="right") - 1, 0, 4)
