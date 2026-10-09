"""oc_stopentry pure rules: stop distance, |w| medians, routing, exposure controls.

All definitions frozen in PLAN.md. Everything here is causal:
- STOP_OFF = 0.0005 (5bps through minute-0 open), frozen ex-ante.
- |w| = absolute post-bear standard-grid book weight (after bear halving,
  BEFORE vol-target/governor/ffill), close-known, variant-independent.
- med_k[sym] uses only standard-grid rows with time in [2021-09-24, A_k - 7d)
  (7-day embargo), finite |w| >= THETA only, >= MIN_OBS else NaN.
- route uses only the issuance bar's |w| vs the frozen med_k.
- control_mult is a mechanical exposure equaliser (diagnostic, in-year).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STOP_OFF = 0.0005
THETA = 0.05
MIN_OBS = 120
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
W_START = pd.Timestamp("2021-09-24", tz="UTC")
EMBARGO = pd.Timedelta(days=7)


def sgn_of(tg: float, theta: float = THETA) -> int:
    """Signal sign with the G2 open threshold (close-known only)."""
    if not np.isfinite(tg):
        return 0
    if abs(float(tg)) < theta:
        return 0
    return int(np.sign(float(tg)))


def stop_price(p0: float, sgn: int, off: float = STOP_OFF) -> float:
    """Stop-entry level through the minute-0 price (breakout side)."""
    return float(p0) * (1.0 + float(sgn) * float(off))


def limit_price(p0: float, sgn: int, off: float) -> float:
    """Passive G2 limit (better-than-open side)."""
    return float(p0) * (1.0 - float(sgn) * float(off))


def stop_fills_long(high_win: np.ndarray, level: float) -> bool | np.ndarray:
    """Strict trade-THROUGH for a long buy-stop: any high > level (touch == no fill)."""
    h = np.asarray(high_win, dtype=float)
    return h > float(level)


def stop_fills_short(low_win: np.ndarray, level: float) -> bool | np.ndarray:
    """Strict trade-THROUGH for a short sell-stop: any low < level."""
    lo = np.asarray(low_win, dtype=float)
    return lo < float(level)


def medians_from_bear(books_bear: pd.DataFrame) -> dict[str, dict[str, float]]:
    """med_k[sym] = median of |w| >= THETA over [2021-09-24, A_k - 7d).

    books_bear: standard-grid post-bear weights (DatetimeIndex UTC, majors columns).
    Median over active (openable) signals only, so V2 chases strength among signals
    rather than vs flat rows. < MIN_OBS finite observations -> NaN (V2 falls back
    to passive for that (anchor, coin); anchor 2021 is empty by construction).
    """
    out: dict[str, dict[str, float]] = {}
    idx = pd.DatetimeIndex(pd.to_datetime(books_bear.index, utc=True))
    vals = books_bear.reindex(columns=list(books_bear.columns))
    for a in ANCH5:
        cut = pd.Timestamp(a, tz="UTC") - EMBARGO
        m = (idx >= W_START) & (idx < cut)
        row: dict[str, float] = {}
        for s in vals.columns:
            v = pd.to_numeric(vals.loc[m, s], errors="coerce").to_numpy(dtype=float)
            v = np.abs(v)
            v = v[np.isfinite(v) & (v >= THETA)]
            row[str(s)] = float(np.median(v)) if len(v) >= MIN_OBS else float("nan")
        out[a] = row
    return out


def route_stop(w_val: float, med: float) -> bool:
    """V2 route for one new entry order: stop iff finite |w| and med and |w| > med."""
    if not (np.isfinite(w_val) and np.isfinite(med)):
        return False
    return bool(abs(float(w_val)) > float(med))


def route_matrix(
    w_grid: np.ndarray, y_of: np.ndarray, meds: dict[str, dict[str, float]], cols: list[str]
) -> np.ndarray:
    """Bool [n, na]: True = stop-entry for a NEW order issued at (i, a).

    w_grid: post-bear |w|-signed weights ffilled to the shifted grid [n, na]
      (signed book weight; abs taken here). y_of: year index per bar.
    """
    n, na = w_grid.shape
    out = np.zeros((n, na), bool)
    for i in range(n):
        y = int(y_of[i])
        for j in range(na):
            wv = w_grid[i, j]
            if not np.isfinite(wv):
                continue
            med = meds[ANCH5[y]][cols[j]]
            if route_stop(float(wv), float(med)):
                out[i, j] = True
    return out


def control_mult(sum_v: float, sum_ref: float) -> float:
    """Per-year constant exposure multiplier c_y = V_filled / REF_filled.

    Fallback 1.0 when REF sum is 0/non-finite or V sum is non-finite (counted).
    """
    if not (np.isfinite(sum_v) and np.isfinite(sum_ref)) or not sum_ref > 0:
        return 1.0
    c = float(sum_v) / float(sum_ref)
    return float(c) if np.isfinite(c) and c > 0 else 1.0
