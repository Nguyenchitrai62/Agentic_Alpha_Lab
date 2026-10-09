"""Pure cascade-breaker helpers for oc_b7breaker (no data access; unit-tested).

Trigger + B7 arithmetic VERBATIM from oc_cascadedelay delay_rule.py /
oc_cascadeboost boost_rule.py / oc_cboostpre cboostpre_rule.py (closes-only >4sg
cascade proxy, market-wide per shift); breaker gate (IDEAS7 #4) added on top.
Outcome-kind branch VERBATIM from oc_presampletilt build_ledger_presample.outcome_mu
(mu=1.0 leg; stop-first ordering) for the stop-rate recompute.

IDEAS7 #4: after any 4h bar with |close-to-close log move| > 4 * trailing-90d sigma,
dip budget x1.5 for 7 days (B7). Circuit breaker: if >= K cascades in trailing M days,
suspend ALL boost (base sizes, mult 1.0). V1 K=2/M=14; V2 K=3/M=21.
Market-wide per shift: triggers on ANY available major gate ALL coins on that shift.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST = 1.5
B7_DAYS = 7
# Breaker variants (frozen integers, IDEAS7 #4 EXACTLY)
V1_K = 2
V1_M = 14
V2_K = 3
V2_M = 21
NS_DAY = 86_400_000_000_000

RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0


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
                 n_days: int = B7_DAYS) -> np.ndarray:
    """B7 window: for each grid time T: True iff exists tc with 0 < T - tc <= n_days.

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


def breaker_active_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                        k: int, m_days: int) -> np.ndarray:
    """Circuit breaker: True at T iff >= k union triggers with tc <= T and T-tc <= m_days.

    Frozen causal reading (PLAN): contemporaneous gate, inclusive both ends
    (tc in [T-Md, T]); tc == T counts (known at T per count<=close). trig_ns sorted.
    Pure.
    """
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(trig_ns, dtype=np.int64)
    out = np.zeros(len(grid_ns), dtype=bool)
    if trig_ns.size == 0:
        return out
    span = int(m_days) * NS_DAY
    # for each T: count tc in [T-span, T] via two searchsorted bounds
    lo_pos = np.searchsorted(trig_ns, grid_ns - span, side="left")
    hi_pos = np.searchsorted(trig_ns, grid_ns, side="right")
    out = (hi_pos - lo_pos) >= int(k)
    return out


def breaker_mult(b7_boosted: np.ndarray, breaker_active: np.ndarray,
                 boost: float = BOOST) -> np.ndarray:
    """Final mult: 1.0 if breaker active else (boost if B7-boosted else 1.0). Pure."""
    b7 = np.asarray(b7_boosted, dtype=bool)
    br = np.asarray(breaker_active, dtype=bool)
    out = np.where(b7, float(boost), 1.0)
    out[br] = 1.0
    return out


def compute_sigma(opens) -> np.ndarray:
    """Presample level sigma VERBATIM build_ledger_presample.compute_sigma.

    pct_change rolling-360 min_periods-120 shift-1 on opens. Pure.
    """
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def find_fill(low_win, level: float):
    """First index with low < level (strict trade-through), else None. Pure."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float = 1.0) -> str:
    """Exit-kind branch VERBATIM build_ledger_presample.outcome_mu ordering.

    Returns one of {"backstop","tp","stop","time"}. Price levels identical to the
    ledger builder; costs omitted (kind only). Pure.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        return "backstop"
    if kt is not None and (ks is None or kt < ks):
        return "tp"
    if ks is not None:
        return "stop"
    return "time"
