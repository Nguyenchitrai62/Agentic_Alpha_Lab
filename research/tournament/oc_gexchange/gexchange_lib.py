"""oc_gexchange pure helpers (pre-registered in PLAN.md; tested in tests/test_oc_gexchange.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd

WIN_24H_NS = 24 * 3600_000_000_000
SIG_WIN = 2160  # 90 days of hourly changes
SIG_MIN = 720  # min valid changes in window
Z_LOW = -1.0
Z_HIGH = 1.0


def raw_d(g0: float, g24: float) -> float:
    """24 h change d = g0 - g24. NaN unless both finite."""
    if not (np.isfinite(g0) and np.isfinite(g24)):
        return float("nan")
    return float(g0 - g24)


def z_of_d(d: float, sigma: float) -> float:
    """z = d / sigma. NaN unless both finite and sigma > 0."""
    if not (np.isfinite(d) and np.isfinite(sigma)):
        return float("nan")
    if not (sigma > 0):
        return float("nan")
    return float(d / sigma)


def assign_bucket(z: float) -> int:
    """0 LOW (z<-1) / 1 MID (-1<=z<=1) / 2 HIGH (z>1); -1 if missing."""
    if not np.isfinite(z):
        return -1
    if z < Z_LOW:
        return 0
    if z > Z_HIGH:
        return 2
    return 1


def idx_24h_before(hour_end_ns: np.ndarray, i0: int) -> int:
    """Index of last hour_end <= hour_end[i0] - 24h. -1 if none/out of range.

    hour_end_ns must be sorted ascending. On a regular hourly grid this is i0-24.
    """
    he = np.asarray(hour_end_ns)
    if i0 < 0 or i0 >= he.size:
        return -1
    target = int(he[i0]) - WIN_24H_NS
    return int(np.searchsorted(he, target, side="right") - 1)


def build_changes(g: np.ndarray, hour_end_ns: np.ndarray) -> np.ndarray:
    """Hourly 24 h-change series c(h) = g[h] - g[j(h)]. NaN unless both finite."""
    g = np.asarray(g, dtype=float)
    he = np.asarray(hour_end_ns)
    n = g.size
    c = np.full(n, np.nan)
    for h in range(n):
        j = idx_24h_before(he, h)
        if j >= 0 and np.isfinite(g[h]) and np.isfinite(g[j]):
            c[h] = g[h] - g[j]
    return c


def trailing_sigma(c: np.ndarray, win: int = SIG_WIN, minp: int = SIG_MIN) -> np.ndarray:
    """Trailing std of c over the `win` predecessors, EXCLUDING current.

    sigma[i] = std(c[i-win:i], ddof=1); NaN if fewer than minp valid.
    Uses only h < i (causal, current change never in its own normalizer).
    """
    s = pd.Series(np.asarray(c, dtype=float))
    return s.shift(1).rolling(win, min_periods=minp).std(ddof=1).to_numpy(dtype=float)


def z_series(g: np.ndarray, hour_end_ns: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Full pipeline on one hourly GEXn series: (d_all, sigma_all, z_all).

    d_all[h] = g[h] - g[j(h)]; sigma_all = trailing_sigma(d-as-c); z = d/sigma.
    """
    g = np.asarray(g, dtype=float)
    he = np.asarray(hour_end_ns)
    c = build_changes(g, he)  # c IS the d series on the hourly grid
    sig = trailing_sigma(c)
    z = np.full(g.size, np.nan)
    m = np.isfinite(c) & np.isfinite(sig) & (sig > 0)
    z[m] = c[m] / sig[m]
    return c, sig, z
