"""oc_spreadcost core: pure helpers for spread measurement + B1 dip-replica cost overlay.

Part 1: quoted-spread stats from the top-of-book collector store
(`backend/liquidations.py`, `data/raw/topbook_live/`), read-only.
Part 2: B1 dip-ladder replica. Fill/sizing/exit definitions are an exact copy
of the frozen oc_b1deeper/oc_venuegap B1+D0 replica (static resting bid at
lv, STRICT low < lv fill, size 1/(1+n) with the v399 n detector, D0 exits from
the actual fill price, maker 0.0002 / taker 0.00055, longs pay 0.0001 funding
on settling timeouts, stop-first priority). Run here on 4 phase-shifted 4h
grids (clock shifts 0..3h, as in oc_phasedisp), R2 depths, 5 years, Binance 1m
(no row with open_time >= 2026-09-24 00:00 UTC is ever used).

No I/O here (see run.py). All functions are pure / unit-testable.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
PHASES = (0, 1, 2, 3)
TAKER_HOWS = ("stop", "backstop", "time")
STOP_HOWS = ("stop", "backstop")  # stop-like exits take the p90 spread charge


# ------------------------------------------------------------------ spreads
def spread_bps(bid, ask):
    """Quoted spread in bps: (ask-bid)/mid*1e4. Invalid quotes -> NaN."""
    b = np.asarray(bid, dtype=float)
    a = np.asarray(ask, dtype=float)
    mid = (b + a) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / mid * 1e4
    bad = ~(np.isfinite(b) & np.isfinite(a) & (b > 0) & (a > 0) & (a > b))
    return np.where(bad, np.nan, out)


def summarize(x) -> dict:
    """Distribution summary over finite values (bps). Empty -> zeros."""
    v = np.asarray(x, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "p99": 0.0, "max": 0.0}
    return {"n": int(len(v)), "mean": float(np.mean(v)), "median": float(np.median(v)),
            "p90": float(np.percentile(v, 90)), "p99": float(np.percentile(v, 99)),
            "max": float(np.max(v))}


def top_volatile_minutes(minute_ms, mids, spreads, top_n: int = 20, min_n: int = 20) -> dict:
    """Rank 1m buckets by mid-price range; spread stats inside the top buckets.

    minute_ms/mids/spreads are aligned arrays over valid rows only.
    Volatility of a minute = (max(mid)-min(mid))/mean(mid)*1e4 in bps.
    Only minutes with >= min_n samples rank (avoids coverage-edge minutes).
    Returns {"minutes": [{minute_ms, n, range_bps}], "spread": summarize(...)}.
    """
    minute_ms = np.asarray(minute_ms, dtype=np.int64)
    mids = np.asarray(mids, dtype=float)
    spreads = np.asarray(spreads, dtype=float)
    if len(minute_ms) == 0:
        return {"minutes": [], "spread": summarize([])}
    keys, inv = np.unique(minute_ms, return_inverse=True)
    n = np.bincount(inv)
    with np.errstate(divide="ignore", invalid="ignore"):
        mn = np.bincount(inv, weights=np.where(np.isfinite(mids), mids, np.nan))
    mx_lo = np.full(len(keys), np.inf)
    mx_hi = np.full(len(keys), -np.inf)
    np.minimum.at(mx_lo, inv, np.where(np.isfinite(mids), mids, np.inf))
    np.maximum.at(mx_hi, inv, np.where(np.isfinite(mids), mids, -np.inf))
    mean = mn / np.maximum(n, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rng = (mx_hi - mx_lo) / mean * 1e4
    order = [i for i in range(len(keys))
             if n[i] >= min_n and np.isfinite(rng[i])]
    order.sort(key=lambda i: -rng[i])
    top = order[:top_n]
    top_set = set(int(keys[i]) for i in top)
    mask = np.array([int(m) in top_set for m in minute_ms])
    minutes = [{"minute_ms": int(keys[i]), "n": int(n[i]), "range_bps": float(rng[i])}
               for i in top]
    return {"minutes": minutes, "spread": summarize(spreads[mask])}


# ------------------------------------------------------------------ B1 replica (frozen copy of oc_b1deeper/oc_venuegap)
def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W), values 0..4."""
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def size_mult(n_fill: int) -> float:
    """B1 size multiplier: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if no touch."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica from the actual fill price px. Returns (ret, x, how).

    x = exit offset (0..239 inside the bar, 240 = next-bar open).
    how in {"tp","stop","backstop","time"}. NaN ret when missing exit price.
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        fill_px = bl if ox > bl else ox
        return (fill_px / px - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / px - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            ex, x = float(Oa[km + 1]), km + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "stop")
        ret = ex / px - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    return (float(o2) / px - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time")


# ------------------------------------------------------------------ cost overlay + grid/time helpers
def apply_extra_cost(ret: float, how: str, extra_med: float, extra_p90: float) -> float:
    """Half-spread realism overlay on taker exits (fractions of fill price).

    TP (maker) legs are unchanged; stop/backstop legs pay 0.5 * p90 spread
    (stops fire in volatile minutes); timeout legs pay 0.5 * median spread.
    """
    if how == "tp":
        return float(ret)
    if how in STOP_HOWS:
        return float(ret) - float(extra_p90)
    if how == "time":
        return float(ret) - float(extra_med)
    return float(ret)


def phase_bar_starts(n_all: int, shift_h: int, bar_len: int = 240) -> np.ndarray:
    """Bar-start minute indices for a 4h grid shifted by shift_h hours."""
    off = int(shift_h) * 60
    return np.arange(off, n_all - bar_len, bar_len, dtype=np.int64)


def year_of(t0, anchors, year_end) -> int | None:
    """Anchor year by bar-open time: Y_k = [A_k, A_k+365d)."""
    for i in range(len(anchors)):
        lo = anchors[i]
        hi = anchors[i + 1] if i < len(anchors) - 1 else year_end
        if lo <= t0 < hi:
            return i
    return None


def daily_path(recs):
    """Exit-date daily sums -> (S, worst_day, max_dd, ndays). max_dd >= 0."""
    if not recs:
        return 0.0, 0.0, 0.0, 0
    daily: dict[str, float] = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)
