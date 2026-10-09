"""oc_vrpstrangle: pure Black-Scholes + fee/size/strike helpers (no I/O).

Assignment: docs/opencode/OPENCODE_W_oc_vrpstrangle.md, PLAN.md in this folder.
All functions are causal by construction: callers pass only as-of-known values.
r = q = 0 throughout. BS core copies oc_vrpstraddle mechanics; the strangle
strike rule (z x sigma OTM, put DOWN / call UP to the grid) is new here.
"""
from __future__ import annotations

import math

import numpy as np

YEAR_DAYS = 365.0


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _ncdf_vec(x: np.ndarray) -> np.ndarray:
    v = np.vectorize(lambda t: 0.5 * (1.0 + math.erf(t / math.sqrt(2.0))))
    return v(np.asarray(x, dtype=float))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """European call, r = q = 0. T in years. T<=0 or sigma<=0 -> intrinsic."""
    S = float(S)
    K = float(K)
    if not (np.isfinite(S) and np.isfinite(K)) or S <= 0 or K <= 0:
        return float("nan")
    intrinsic = max(S - K, 0.0)
    if not np.isfinite(T) or T <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return intrinsic
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sqt
    d2 = d1 - sqt
    return float(S * _ncdf(d1) - K * _ncdf(d2))


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
    return float(K * _ncdf(-d2) - S * _ncdf(-d1))


def bs_call_vec(S: np.ndarray, K: float, T: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    out = np.maximum(S - K, 0.0)
    ok = np.isfinite(S) & np.isfinite(T) & np.isfinite(sigma) & (S > 0) & (T > 0) & (sigma > 0)
    if np.any(ok):
        sqt = sigma[ok] * np.sqrt(T[ok])
        d1 = (np.log(S[ok] / K) + 0.5 * sigma[ok] ** 2 * T[ok]) / sqt
        d2 = d1 - sqt
        out[ok] = S[ok] * _ncdf_vec(d1) - K * _ncdf_vec(d2)
    return out


def bs_put_vec(S: np.ndarray, K: float, T: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    out = np.maximum(K - S, 0.0)
    ok = np.isfinite(S) & np.isfinite(T) & np.isfinite(sigma) & (S > 0) & (T > 0) & (sigma > 0)
    if np.any(ok):
        sqt = sigma[ok] * np.sqrt(T[ok])
        d1 = (np.log(S[ok] / K) + 0.5 * sigma[ok] ** 2 * T[ok]) / sqt
        d2 = d1 - sqt
        out[ok] = K * _ncdf_vec(-d2) - S[ok] * _ncdf_vec(-d1)
    return out


def strangle_strikes(S: float, sig_p: float, sig_c: float, T: float,
                     z: float, grid: float) -> tuple[float, float]:
    """OTM strangle strikes: put DOWN / call UP to the grid.

    K_p = floor(S*exp(-z*sig_p*sqrt(T)) / grid) * grid,
    K_c = ceil(S*exp(+z*sig_c*sqrt(T)) / grid) * grid.
    Returns (nan, nan) on bad inputs.
    """
    if not (np.isfinite(S) and np.isfinite(sig_p) and np.isfinite(sig_c)
            and np.isfinite(T) and np.isfinite(z) and np.isfinite(grid)):
        return (float("nan"), float("nan"))
    if S <= 0 or sig_p <= 0 or sig_c <= 0 or T <= 0 or z <= 0 or grid <= 0:
        return (float("nan"), float("nan"))
    raw_p = S * math.exp(-z * sig_p * math.sqrt(T))
    raw_c = S * math.exp(+z * sig_c * math.sqrt(T))
    Kp = math.floor(raw_p / grid) * grid
    Kc = math.ceil(raw_c / grid) * grid
    if Kp <= 0 or Kc <= 0 or Kp >= Kc:
        return (float("nan"), float("nan"))
    return (float(Kp), float(Kc))


def fee_per_side(S_trade: float, leg_price: float, cap_rate: float = 0.0003) -> float:
    """Deribit-style option fee per leg per side: min(cap_rate*S, 0.125*price)."""
    if not (np.isfinite(S_trade) and np.isfinite(leg_price)) or leg_price < 0:
        return float("nan")
    return min(cap_rate * S_trade, 0.125 * leg_price)


def settle_fee(S_settle: float, intrinsic: float, rate: float = 0.00015) -> float:
    """Settlement fee if ITM: min(rate*S, 0.125*intrinsic)."""
    if not (np.isfinite(S_settle) and np.isfinite(intrinsic)):
        return float("nan")
    if intrinsic <= 0:
        return 0.0
    return min(rate * S_settle, 0.125 * intrinsic)


def size_q(equity_at_entry: float, S: float, f: float = 1.0) -> float:
    """Short-strangle units per coin: q = 0.5*f*E / S (notional 0.5 f E)."""
    if not (np.isfinite(equity_at_entry) and np.isfinite(S)) or S <= 0 or equity_at_entry < 0:
        return 0.0
    return 0.5 * f * equity_at_entry / S
