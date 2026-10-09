"""oc_convttl: conviction-dependent order TTL (IDEAS8 #7) pure helpers.

Frozen definitions in PLAN.md. No I/O, no fits, no test-year statistics.
TTL varies only resting TIME (n_valid 2 vs 1 bars); price/offsets frozen (G2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_LONG = 2
N_SHORT = 1


def ttl_for_weight(absw: float, q: float) -> int:
    """Conviction TTL in bars: 2 if |w_base| > q else 1 (strict >, ties go short).

    Non-finite inputs never occur (books fillna 0.0); if one did, it goes short
    (safe default, disclosed).
    """
    try:
        if np.isfinite(absw) and np.isfinite(q) and float(absw) > float(q):
            return N_LONG
    except Exception:
        pass
    return N_SHORT


def mean_ttl_scale(p: float) -> float:
    """Mean-TTL weight scale for the exposure-matched control: (1+p)/2."""
    return (1.0 + float(p)) / 2.0


def year_index(ts: pd.Timestamp, shift_h: int,
               anchors=("2021-09-24", "2022-09-24", "2023-09-24",
                         "2024-09-24", "2025-09-24")) -> int | None:
    """Anchor-year index k for timestamp ts on the shift_h clock.

    Year k = [A_k + shift, A_k + shift + 365d). None when outside all years
    (pre-live warmup; caller falls back to year 0's threshold — frozen).
    """
    sh = pd.Timedelta(hours=int(shift_h))
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    for k, a in enumerate(anchors):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        if a0 <= t < a0 + pd.Timedelta(days=365):
            return k
    return None


def thresholds_for_bars(idx: pd.DatetimeIndex, shift_h: int, qs: list[float]) -> np.ndarray:
    """Per-bar threshold array aligned to idx (shifted clock).

    qs[k] = threshold for anchor year k (q50 or q75). Bars outside all years
    fall back to qs[0] (frozen; non-live bars skip trading anyway).
    """
    out = np.full(len(idx), float(qs[0]), dtype=float)
    for n, t in enumerate(idx):
        k = year_index(t, shift_h)
        if k is not None:
            out[n] = float(qs[k])
    return out
