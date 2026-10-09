"""oc_btcresid pure rule helpers (no data access; unit-tested).

Causal contract: 4h log returns use only closes <= T; betas are frozen per-anchor
OLS slopes over [A-372d, A-7d); residual rows use close-known weights + pre-anchor
betas only; NaN beta -> 0.0 (no adjustment); T < 2021-09-24 never adjusted.
"""
from __future__ import annotations

import numpy as np

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
MIN_PAIRS = 100


def ols_beta(x: np.ndarray, y: np.ndarray) -> float:
    """OLS slope of y on x (with intercept); NaN if degenerate.

    x = BTC 4h returns, y = coin 4h returns, pairwise-finite only.
    beta = sum((x-xb)(y-yb)) / sum((x-xb)^2); NaN if < MIN_PAIRS pairs
    or zero variance / non-finite.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    xs, ys = x[m], y[m]
    if xs.size < MIN_PAIRS:
        return float("nan")
    xb, yb = float(xs.mean()), float(ys.mean())
    dx = xs - xb
    den = float(dx @ dx)
    if not np.isfinite(den) or den <= 0:
        return float("nan")
    num = float(dx @ (ys - yb))
    out = num / den
    return float(out) if np.isfinite(out) else float("nan")


def clip01(b: float) -> float:
    """Clip beta to [0,1]; NaN -> 0.0 (frozen V2 rule)."""
    if not np.isfinite(b):
        return 0.0
    return float(min(max(float(b), 0.0), 1.0))


def beta_for_use(beta: float, clip: bool) -> float:
    """Effective beta: NaN -> 0.0; V2 clips to [0,1], V1 raw."""
    if not np.isfinite(beta):
        return 0.0
    if clip:
        return clip01(float(beta))
    return float(beta)


def resid_row(w: dict | np.ndarray, w_btc: float, beta: float, clip: bool = False) -> float:
    """Single-coin residual: w_c - b * w_BTC (pure scalar helper)."""
    return float(w) - beta_for_use(float(beta), clip) * float(w_btc)


def resid_frame(sb: object, betas: dict, clip: bool = False) -> object:
    """Whole book-row residual on a DataFrame (post-bear, NaN->0).

    sb: DataFrame indexed by standard-grid T with COINS columns.
    betas: {coin: beta} for the row's anchor year (BTC entry ignored, ==1).
    Returns a new DataFrame with the same index/columns.
    """
    import pandas as pd  # local import: keeps module importable without pandas

    out = sb.copy()
    wbtc = sb["BTCUSDT"].fillna(0.0).to_numpy(dtype=float)
    for c in COINS:
        if c == "BTCUSDT":
            out[c] = 0.0
            continue
        b = beta_for_use(float(betas.get(c, float("nan"))), clip)
        wc = sb[c].fillna(0.0).to_numpy(dtype=float)
        out[c] = wc - b * wbtc
    return out


def anchor_of(T_ns: np.ndarray, anch_ns: np.ndarray) -> np.ndarray:
    """Index of the anchor year each timestamp belongs to (right-closed)."""
    T_ns = np.asarray(T_ns, dtype=np.int64)
    anch_ns = np.asarray(anch_ns, dtype=np.int64)
    return np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)


def control_mult(mean_variant: float, mean_ref: float) -> float:
    """Exposure-matched constant: realised mean gross scale variant / ref.

    Both means are >= 0 gross exposures; returns 1.0 if ref mean is 0/non-finite.
    """
    mv, mr = float(mean_variant), float(mean_ref)
    if not np.isfinite(mv) or not np.isfinite(mr) or mr <= 0:
        return 1.0
    out = mv / mr
    return float(out) if np.isfinite(out) and out >= 0 else 1.0
