"""oc_putwrite: weekly cash-secured put-write helpers (pure, no I/O).

Assignment: docs/opencode/OPENCODE_W_oc_putwrite.md, PLAN.md in this folder.
All functions are causal by construction: callers pass only as-of-known values.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

YEAR_DAYS = 365.0
SQRT_TAU = math.sqrt(7.0 / 365.0)  # 7-day expiry


def bs_put(S: float, K: float, T: float, sigma: float) -> float:
    """European put, r = q = 0. T in years. T<=0 or sigma<=0 -> intrinsic."""
    S = float(S)
    K = float(K)
    if not (np.isfinite(S) and np.isfinite(K)) or S <= 0 or K <= 0:
        return float("nan")
    intrinsic = max(K - S, 0.0)
    if not np.isfinite(T) or T <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return intrinsic
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sqt
    d2 = d1 - sqt
    return float(K * norm.cdf(-d2) - S * norm.cdf(-d1))


def bs_put_vec(S: np.ndarray, K: float, T: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Vectorised European put (r=q=0); falls back to intrinsic elementwise."""
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    out = np.maximum(K - S, 0.0)
    ok = np.isfinite(S) & np.isfinite(T) & np.isfinite(sigma) & (S > 0) & (T > 0) & (sigma > 0)
    if np.any(ok):
        sqt = sigma[ok] * np.sqrt(T[ok])
        d1 = (np.log(S[ok] / K) + 0.5 * sigma[ok] ** 2 * T[ok]) / sqt
        d2 = d1 - sqt
        out[ok] = K * norm.cdf(-d2) - S[ok] * norm.cdf(-d1)
    return out


def strike_from_spot(S: float, z: float, sigma_e: float, grid: float) -> float:
    """K = S*exp(-z*sigma_e*sqrt(7/365)) rounded DOWN to strike grid."""
    if not (np.isfinite(S) and np.isfinite(sigma_e)) or S <= 0 or sigma_e <= 0 or grid <= 0:
        return float("nan")
    raw = S * math.exp(-z * sigma_e * SQRT_TAU)
    return math.floor(raw / grid) * grid


def fee_per_side(S_trade: float, option_price: float, cap_rate: float = 0.0003) -> float:
    """Deribit-style taker cap per side per unit: min(cap_rate*S, 0.125*price)."""
    if not (np.isfinite(S_trade) and np.isfinite(option_price)) or option_price < 0:
        return float("nan")
    return min(cap_rate * S_trade, 0.125 * option_price)


def settle_fee(S_settle: float, intrinsic: float) -> float:
    """Settlement fee if ITM: min(0.00015*S, 0.125*intrinsic)."""
    return min(0.00015 * S_settle, 0.125 * intrinsic)


def size_naked(equity_at_entry: float, K: float, f: float = 1.0) -> float:
    """Cash-secured naked put units: q = 0.5*f*E / K (collateral q*K = 0.5 f E)."""
    if not (np.isfinite(equity_at_entry) and np.isfinite(K)) or K <= 0 or equity_at_entry < 0:
        return 0.0
    return 0.5 * f * equity_at_entry / K


def size_spread(equity_at_entry: float, k_short: float, k_long: float, f: float = 1.0) -> float:
    """Defined-risk spread units: collateral q*(Ks-Kl) = 0.5 f E."""
    width = k_short - k_long
    if not (np.isfinite(equity_at_entry) and np.isfinite(width)) or width <= 0 or equity_at_entry < 0:
        return 0.0
    return 0.5 * f * equity_at_entry / width


def weekly_pnl_per_unit(
    premium: float,
    fee_in: float,
    exit_kind: str,
    exit_mark: float = 0.0,
    fee_out: float = 0.0,
    intrinsic: float = 0.0,
    settle: float = 0.0,
) -> float:
    """Net P&L per short-put unit. exit_kind in {tp, sl, expiry}."""
    if exit_kind in ("tp", "sl"):
        return premium - fee_in - exit_mark - fee_out
    if exit_kind == "expiry":
        return premium - fee_in - intrinsic - settle
    raise ValueError(exit_kind)
