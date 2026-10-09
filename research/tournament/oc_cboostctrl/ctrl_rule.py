"""Pure helpers for oc_cboostctrl (no data access; unit-tested).

Cascade arithmetic VERBATIM from oc_cascadeboost boost_rule.py (= oc_cascadedelay
delay_rule.py): closes-only >4sg triggers, strictly-after 7d windows, mult 1.5.
Adds the frozen control builders: per-year constants (CTRL_C, mechanical) and
deterministic random 7-day windows (CTRL_R, frozen seeds).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST = 1.5
N_DAYS = 7
N_SEEDS = 20
SEED_BASE = 6100000
NS_DAY = 86_400_000_000_000


def close_returns(closes) -> np.ndarray:
    """Close-to-close log returns; r[0] = NaN. Pure."""
    c = np.asarray(closes, dtype=float)
    r = np.full_like(c, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.log(c[1:] / c[:-1])
    r[~np.isfinite(r)] = np.nan
    return r


def trailing_sigma(r, window: int = WINDOW,
                   min_periods: int = MIN_PERIODS) -> np.ndarray:
    """SIG[i] = std(ddof=1) of r[i-window .. i-1] (tested bar EXCLUDED)."""
    r = np.asarray(r, dtype=float)
    n = r.size
    out = np.full(n, np.nan)
    if n == 0:
        return out
    finite = np.isfinite(r)
    cs = np.cumsum(np.where(finite, r, 0.0))
    cs2 = np.cumsum(np.where(finite, r * r, 0.0))
    cn = np.cumsum(finite.astype(float))
    for i in range(n):
        lo = max(0, i - window)
        cnt = cn[i - 1] - (cn[lo - 1] if lo > 0 else 0.0) if i > 0 else 0.0
        if cnt < min_periods:
            continue
        s = cs[i - 1] - (cs[lo - 1] if lo > 0 else 0.0)
        s2 = cs2[i - 1] - (cs2[lo - 1] if lo > 0 else 0.0)
        var = (s2 - s * s / cnt) / (cnt - 1)
        if np.isfinite(var) and var > 0:
            out[i] = float(np.sqrt(var))
    return out


def triggers_of(closes, thresh: float = THRESH, window: int = WINDOW,
                min_periods: int = MIN_PERIODS) -> np.ndarray:
    """Bool array: bar i fires iff |r[i]| > thresh * SIG[i] (strict)."""
    r = close_returns(closes)
    sig = trailing_sigma(r, window, min_periods)
    fire = np.zeros(len(r), dtype=bool)
    ok = np.isfinite(r) & np.isfinite(sig) & (sig > 0)
    fire[ok] = np.abs(r[ok]) > float(thresh) * sig[ok]
    return fire


def boosted_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                 n_days: int = N_DAYS) -> np.ndarray:
    """For each grid time T: True iff exists tc with 0 < T - tc <= n_days."""
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(trig_ns, dtype=np.int64)
    out = np.zeros(len(grid_ns), dtype=bool)
    if trig_ns.size == 0:
        return out
    span = int(n_days) * NS_DAY
    pos = np.searchsorted(trig_ns, grid_ns, side="left") - 1
    valid = pos >= 0
    out[valid] = (grid_ns[valid] - trig_ns[pos[valid]] <= span)
    return out


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift."""
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


def seed_of(y: int, s: int, j: int) -> int:
    """Frozen deterministic seed for CTRL_R year y, shift s, seed-index j."""
    return int(SEED_BASE) + int(j) * 100 + int(y) * 10 + int(s)


def random_starts_for(n_grid: int, k: int, rng) -> np.ndarray:
    """Sorted distinct grid positions for k random window starts.

    Without replacement (k >= n_grid -> all positions). Pure given rng.
    """
    n = int(n_grid)
    k = int(k)
    if n <= 0 or k <= 0:
        return np.empty(0, dtype=np.int64)
    if k >= n:
        return np.arange(n, dtype=np.int64)
    return np.sort(rng.choice(n, size=k, replace=False)).astype(np.int64)
