"""oc_gex pure helpers (pre-registered; tested in tests/test_oc_gex.py)."""
from __future__ import annotations

import numpy as np

SQRT2PI = np.sqrt(2.0 * np.pi)
YEAR_SEC = 365.25 * 86400.0
IV_LO, IV_HI = 0.05, 3.0
T_FLOOR_Y = 1.0 / 8760.0


def gamma_bs(S: float, K: float, iv: float, T: float) -> float:
    """Black-Scholes gamma (r=0, same for C/P). NaN on bad input."""
    if not (np.isfinite(S) and np.isfinite(K) and np.isfinite(iv) and np.isfinite(T)):
        return float("nan")
    iv = min(max(float(iv), IV_LO), IV_HI)
    T = max(float(T), T_FLOOR_Y)
    if not (S > 0 and K > 0 and iv > 0 and T > 0):
        return float("nan")
    sq = iv * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * iv * iv * T) / sq
    return float(np.exp(-0.5 * d1 * d1) / SQRT2PI / (S * sq))


def dealer_gex(q: np.ndarray, gam: np.ndarray, S: float) -> float:
    """GEX = -sum q*gamma*S^2*0.01."""
    q = np.asarray(q, dtype=float)
    gam = np.asarray(gam, dtype=float)
    m = np.isfinite(q) & np.isfinite(gam)
    if not m.any() or not np.isfinite(S) or S <= 0:
        return float("nan")
    return float(-np.sum(q[m] * gam[m] * S * S * 0.01))


def gexn(gex: float, S: float, n30: float) -> float:
    """Dollar-notional normalisation GEX/(S*N30). NaN unless all finite/positive."""
    if not (np.isfinite(gex) and np.isfinite(S) and np.isfinite(n30)):
        return float("nan")
    if not (S > 0 and n30 > 0):
        return float("nan")
    return float(gex / (S * n30))


def tercile_cuts(x: np.ndarray) -> tuple[float, float]:
    """33rd/66th percentiles of finite training values (embargo applied by caller)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return (float("nan"), float("nan"))
    return (float(np.quantile(x, 1.0 / 3.0)), float(np.quantile(x, 2.0 / 3.0)))


def assign_tercile(v: float, lo: float, hi: float) -> int:
    """0 bottom / 1 middle / 2 top; -1 if missing or cuts missing."""
    if not (np.isfinite(v) and np.isfinite(lo) and np.isfinite(hi)):
        return -1
    if v <= lo:
        return 0
    if v >= hi:
        return 2
    return 1


def last_hour_before(hour_end_ns: np.ndarray, t_ns: int) -> int:
    """Index of last hour_end with hour_end <= t_ns - 60s. -1 if none.

    hour_end_ns must be sorted ascending. Join key: last full hour strictly
    before the bar open (1-minute safety margin).
    """
    return int(np.searchsorted(np.asarray(hour_end_ns), int(t_ns) - 60_000_000_000, side="right") - 1)
