"""Pure tapered-boost helpers for oc_b7taper (no data access; unit-tested).

Trigger arithmetic VERBATIM from oc_cascadedelay delay_rule.py /
oc_cascadeboost boost_rule.py / oc_cboostpre cboostpre_rule.py
(closes-only >4sg cascade proxy, market-wide per shift); the ONLY new logic is
the taper (IDEAS7 #1): the boost decays with days since the latest cascade.

IDEAS: after a 4h bar with |close-to-close log move| > 4 * trailing-90d sigma,
dip budget is multiplied by a taper f(d) for 7 days, where d = days since the
latest union trigger strictly before the decision bar:
  V1 step:  1.6 if floor(d) in {0,1,2}; 1.3 if in {3,4,5}; 1.0 if in {6,7}.
  V2 exp:   1 + 0.5 * 2^(-d/3) with d float (calendar days).
Outside (tc, tc+7d] mult = 1.0. Market-wide per shift.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST_DAYS = 7
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
V1_HI = 1.6
V1_MID = 1.3
V1_LO = 1.0
V2_BASE = 1.0
V2_AMP = 0.5
V2_HALF = 3.0
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
    """SIG[i] = std(ddof=1) of r[i-window .. i-1] (tested bar EXCLUDED).

    Requires >= min_periods finite values, else NaN. Pure; causal by
    construction (only strictly-prior returns enter SIG[i]).
    """
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
    """Bool array: bar i fires iff |r[i]| > thresh * SIG[i] (strict).

    SIG[i] excludes r[i] (no self-inclusion). NaN SIG / non-finite r -> False.
    Pure.
    """
    r = close_returns(closes)
    sig = trailing_sigma(r, window, min_periods)
    fire = np.zeros(len(r), dtype=bool)
    ok = np.isfinite(r) & np.isfinite(sig) & (sig > 0)
    fire[ok] = np.abs(r[ok]) > float(thresh) * sig[ok]
    return fire


def taper_mult(d_days: float, variant: str) -> float:
    """Taper multiplier for scalar days-since-trigger (float, >= 0). Pure.

    V1: floor bins {0,1,2} -> 1.6; {3,4,5} -> 1.3; {6,7} -> 1.0.
    V2: 1 + 0.5 * 2^(-d/3).
    """
    import math

    d = float(d_days)
    if variant == "V1":
        b = math.floor(d)
        if b in (0, 1, 2):
            return V1_HI
        if b in (3, 4, 5):
            return V1_MID
        return V1_LO
    if variant == "V2":
        return V2_BASE + V2_AMP * (2.0 ** (-d / V2_HALF))
    raise ValueError(variant)


def mults_on_grid(grid_ns: np.ndarray, trig_ns: np.ndarray):
    """Per-grid-time (mult_V1, mult_V2, d_days) from sorted union triggers.

    For each T: tc_last = latest trig strictly before T; if none or
    T - tc_last > 7d -> (1.0, 1.0, nan). Else d = (T-tc_last)/day and the
    frozen V1/V2 taper. Pure; causal (searchsorted left-1).
    """
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(np.sort(np.asarray(trig_ns, dtype=np.int64)),
                         dtype=np.int64)
    m1 = np.ones(len(grid_ns), dtype=float)
    m2 = np.ones(len(grid_ns), dtype=float)
    dd = np.full(len(grid_ns), np.nan, dtype=float)
    if trig_ns.size == 0:
        return m1, m2, dd
    span = int(BOOST_DAYS) * NS_DAY
    pos = np.searchsorted(trig_ns, grid_ns, side="left") - 1
    for j in np.where(pos >= 0)[0]:
        dt = int(grid_ns[j]) - int(trig_ns[pos[j]])
        if dt <= 0 or dt > span:
            continue
        d = dt / float(NS_DAY)
        dd[j] = d
        b = int(np.floor(d))
        m1[j] = V1_HI if b in (0, 1, 2) else (V1_MID if b in (3, 4, 5) else V1_LO)
        m2[j] = V2_BASE + V2_AMP * (2.0 ** (-d / V2_HALF))
    return m1, m2, dd


def boosted_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                 n_days: int = BOOST_DAYS) -> np.ndarray:
    """For each grid time T: True iff exists tc with 0 < T - tc <= n_days.

    Both arrays int64 ns; trig_ns must be sorted. Pure (searchsorted on the
    latest tc strictly before T). Kept for verbatim-arithmetic tests.
    """
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


# Alias kept so the verbatim-inherited arithmetic reads identically.
cooled_mask = boosted_mask


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention
    as oc_crashgate/oc_kronosmanual/oc_cascadedelay)."""
    sh = pd.Timedelta(hours=shift)
    live1 = pd.Timestamp(y1, tz="UTC") + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp("2021-09-24", tz="UTC") + sh:
        return 0
    for y, a in enumerate(("2021-09-24", "2022-09-24", "2023-09-24",
                           "2024-09-24", "2025-09-24")):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return 4
