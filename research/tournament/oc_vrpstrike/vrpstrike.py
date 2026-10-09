"""oc_vrpstrike: Black-Scholes + fee/size/selection helpers (no I/O).

Assignment: docs/opencode/OPENCODE_W_oc_vrpstrike.md, PLAN.md in this folder.
Frozen rule STRIKE-V2 (V2-unhedged mechanics, traded-IV pricing).
All functions are causal by construction: callers pass only as-of-known values.
r = q = 0 throughout. Same BS/fee/size maths as oc_vrpstraddle/vrp.py
(copied here so this folder is self-contained; sibling files not touched).
"""
from __future__ import annotations

import math

import numpy as np

YEAR_DAYS = 365.0
MIN_ENTRY_AMOUNT = 0.1  # coin; per leg over the Fri 08:00-10:59 window
HAIRCUIT = {"BTC": 0.5, "ETH": 1.0}  # vol points; ask = mid + h, sell = mid - h
FALLBACK_LOOKBACK_NS = 24 * 3600 * 1_000_000_000


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """European call, r = q = 0. T in years. T<=0 or sigma<=0 -> intrinsic."""
    S = float(S)
    K = float(K)
    if not (np.isfinite(S) and np.isfinite(K)) or S <= 0 or K <= 0:
        return float("nan")
    intrinsic = max(S - K, 0.0)
    if not np.isfinite(T) or T <= 0 or not np.isfinite(sigma) or sigma <= 0:
        return float(intrinsic)
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
        return float(intrinsic)
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sqt
    d2 = d1 - sqt
    return float(K * _ncdf(-d2) - S * _ncdf(-d1))


def bs_straddle(S: float, K: float, T: float, sigma: float) -> float:
    """Call + put (r = q = 0)."""
    return bs_call(S, K, T, sigma) + bs_put(S, K, T, sigma)


def fee_per_side(S_trade: float, leg_price: float, cap_rate: float = 0.0003) -> float:
    """Deribit-style option fee per leg per side: min(cap_rate*S, 0.125*price)."""
    if not (np.isfinite(S_trade) and np.isfinite(leg_price)) or leg_price < 0:
        return float("nan")
    leg_price = max(float(leg_price), 0.0)  # floor dust-negative BS output at 0
    return min(cap_rate * S_trade, 0.125 * leg_price)


def settle_fee(S_settle: float, intrinsic: float, rate: float = 0.00015) -> float:
    """Settlement fee if ITM: min(rate*S, 0.125*intrinsic)."""
    if not (np.isfinite(S_settle) and np.isfinite(intrinsic)):
        return float("nan")
    if intrinsic <= 0:
        return 0.0
    return min(rate * S_settle, 0.125 * intrinsic)


def size_q(equity_at_entry: float, S: float, f: float = 1.0) -> float:
    """Short-straddle units per coin: q = 0.5*f*E / S (notional 0.5 f E)."""
    if not (np.isfinite(equity_at_entry) and np.isfinite(S)) or S <= 0 or equity_at_entry < 0:
        return 0.0
    return 0.5 * f * equity_at_entry / S


def amount_weighted_iv(ivs: np.ndarray, amts: np.ndarray) -> tuple[float, float]:
    """Amount-weighted vwap_iv over buckets. Returns (iv, total_amount)."""
    ivs = np.asarray(ivs, dtype=float)
    amts = np.asarray(amts, dtype=float)
    tot = float(np.nansum(amts))
    if not np.isfinite(tot) or tot <= 0:
        return float("nan"), 0.0
    mask = np.isfinite(ivs) & np.isfinite(amts) & (amts > 0)
    if not np.any(mask):
        return float("nan"), tot
    return float(np.sum(ivs[mask] * amts[mask]) / np.sum(amts[mask])), tot


def select_strike(strikes: np.ndarray, index: float) -> float:
    """Strike nearest to index; ties -> lower strike. NaN if unusable."""
    strikes = np.asarray(strikes, dtype=float)
    strikes = strikes[np.isfinite(strikes)]
    if len(strikes) == 0 or not np.isfinite(index):
        return float("nan")
    d = np.abs(strikes - index)
    best = float(np.min(d))
    cands = strikes[d == best]
    return float(np.min(cands))


def sell_sigma(iv_entry: float, coin: str) -> float:
    """Sell sigma (decimal): (iv_entry - h)/100. NaN-safe (BS floors <=0)."""
    h = HAIRCUIT[coin]
    if not np.isfinite(iv_entry):
        return float("nan")
    return (float(iv_entry) - h) / 100.0


def last_traded_iv(closes: np.ndarray, ivs: np.ndarray, t_ns: int,
                   lookback_ns: int = FALLBACK_LOOKBACK_NS) -> tuple[float, bool]:
    """Latest bucket with close <= t (bucket known at its close; strictly as-of).

    Returns (iv, fresh) where fresh = a trade exists with t-lookback <= close <= t
    and finite iv. Callers fall back to r x DVOL when fresh is False.
    """
    closes = np.asarray(closes, dtype=np.int64)
    ivs = np.asarray(ivs, dtype=float)
    i = int(np.searchsorted(closes, int(t_ns), side="right")) - 1
    if i < 0:
        return float("nan"), False
    if closes[i] < int(t_ns) - int(lookback_ns):
        return float("nan"), False
    iv = float(ivs[i])
    if not np.isfinite(iv):
        return float("nan"), False
    return iv, True
