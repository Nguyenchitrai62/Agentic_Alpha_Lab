"""Pure BTC/ETH-only boost helpers for oc_b7btceth (no data access; unit-tested).

Trigger arithmetic VERBATIM from oc_cascadedelay delay_rule.py /
oc_cascadeboost boost_rule.py / oc_cboostpre cboostpre_rule.py
(closes-only >4sg cascade proxy, market-wide per shift); the ONLY new logic is
the coin mask (IDEAS7 #5): the B7 window mult (1.5 in (tc, tc+7d] else 1.0) is
kept only for fills whose ledger coin is in the frozen mask, else 1.0.

IDEAS: after any 4h bar with |close-to-close log move| > 4 * trailing-90d
sigma, dip budget x1.5 (mult BOOST) for BOOST_DAYS = 7 days, but ONLY for
BTC+ETH rungs (V1, MASK_V1 = {0, 1}) / BTC rungs only (V2, MASK_V2 = {0}).
Other coins keep base size in the window. No sizing-model change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST = 1.5
BOOST_DAYS = 7
MASK_V1 = frozenset((0, 1))  # BTC, ETH on both ledgers
MASK_V2 = frozenset((0,))  # BTC only on both ledgers
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


def boosted_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                 n_days: int) -> np.ndarray:
    """For each grid time T: True iff exists tc with 0 < T - tc <= n_days.

    Both arrays int64 ns; trig_ns must be sorted. Pure (searchsorted on the
    latest tc strictly before T).
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


def apply_mask(b7_mult, coin: int, mask) -> float:
    """Coin-masked mult: 1.5 iff B7-boosted AND coin in mask else 1.0. Pure.

    b7_mult is the market-wide B7 time-bar mult (1.5 or 1.0); coin is the
    ledger coin index; mask is MASK_V1 / MASK_V2. Static per coin, no
    lookahead (coin known at signal time).
    """
    return 1.5 if float(b7_mult) == 1.5 and int(coin) in set(mask) else 1.0


def coin_mult(b7_mult, coin: int, variant: str) -> float:
    """Variant wrapper: V1 -> BTC+ETH mask, V2 -> BTC-only mask. Pure."""
    if variant == "V1":
        return apply_mask(b7_mult, coin, MASK_V1)
    if variant == "V2":
        return apply_mask(b7_mult, coin, MASK_V2)
    raise ValueError(f"unknown variant {variant!r} (want V1/V2)")


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
