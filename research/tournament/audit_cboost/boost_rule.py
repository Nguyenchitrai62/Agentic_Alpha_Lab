"""audit_cboost boost_rule: independent frozen cascade-trigger + boost-window helpers.

No data access. Frozen spec (from PLAN.md, verbatim inherited):
  r[i] = ln(C[i]/C[i-1]); SIG[i] = std(ddof=1) of r[i-540..i-1], min_periods 120;
  trigger iff SIG finite > 0 and |r[i]| > 4.0*SIG[i]; tc = T[i]+4h;
  boosted(T, s) iff exists trigger (any major, same shift) with 0 < T-tc <= 7d.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SIG_WINDOW = 540
SIG_MIN = 120
THRESH = 4.0
B7_DAYS = 7
BOOST = 1.5

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def close_returns(closes: np.ndarray) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    r = np.full_like(c, np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = np.isfinite(c[1:]) & np.isfinite(c[:-1]) & (c[:-1] > 0) & (c[1:] > 0)
        r[1:][ok] = np.log(c[1:][ok] / c[:-1][ok])
    r[~np.isfinite(r)] = np.nan
    return r


def trailing_sigma(returns: np.ndarray, window: int = SIG_WINDOW,
                   min_periods: int = SIG_MIN) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    n = len(r)
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - window)
        seg = r[lo:i]  # strictly before i: excludes tested bar
        seg = seg[np.isfinite(seg)]
        if len(seg) >= min_periods:
            s = float(np.std(seg, ddof=1))
            out[i] = s if np.isfinite(s) and s > 0 else np.nan
    return out


def triggers_of(T: np.ndarray, closes: np.ndarray,
                thresh: float = THRESH) -> np.ndarray:
    """Bool per bar: fires iff SIG finite>0 and |r| > thresh*SIG. tc = T+4h."""
    T = pd.to_datetime(np.asarray(T), utc=True)
    r = close_returns(np.asarray(closes, dtype=float))
    sig = trailing_sigma(r)
    fire = np.zeros(len(r), dtype=bool)
    ok = np.isfinite(r) & np.isfinite(sig) & (sig > 0)
    fire[ok] = np.abs(r[ok]) > thresh * sig[ok]
    return fire


def trigger_close_times(T: np.ndarray, fires: np.ndarray) -> pd.DatetimeIndex:
    T = pd.to_datetime(np.asarray(T), utc=True)
    return pd.DatetimeIndex(T[np.asarray(fires, dtype=bool)] + pd.Timedelta(hours=4))


def boosted_mask(grid_T: np.ndarray, trigger_tcs: np.ndarray,
                 n_days: int = B7_DAYS) -> np.ndarray:
    """Market-wide per shift: boosted iff exists tc with 0 < T-tc <= n_days."""
    G = pd.to_datetime(np.asarray(grid_T), utc=True)
    tc = pd.to_datetime(np.asarray(trigger_tcs), utc=True)
    tc = np.sort(tc.values.astype("datetime64[ns]").astype(np.int64))
    g = G.values.astype("datetime64[ns]").astype(np.int64)
    out = np.zeros(len(g), dtype=bool)
    if len(tc) == 0:
        return out
    win_ns = int(n_days) * 86400 * 10 ** 9
    # latest tc strictly before T: searchsorted left - 1
    pos = np.searchsorted(tc, g, side="left") - 1
    ok = pos >= 0
    out[ok] = (g[ok] - tc[pos[ok]] > 0) & (g[ok] - tc[pos[ok]] <= win_ns)
    return out


def anchor_of(H: pd.Timestamp) -> int:
    """Latest anchor index <= H (standard anchors, shift-agnostic)."""
    a = [pd.Timestamp(x, tz="UTC").value for x in ANCH5]
    h = pd.Timestamp(H, tz="UTC").value
    import bisect
    return int(min(max(bisect.bisect_right(a, h) - 1, 0), 4))
