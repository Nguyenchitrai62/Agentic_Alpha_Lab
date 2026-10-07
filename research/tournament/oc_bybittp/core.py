"""oc_bybittp core: venue-native B1 fill + D0-from-fill exit + TP near-miss.

Pure numpy, no I/O. Frozen definitions in PLAN.md: B1 replica per venue
(static bid at the venue-native level, STRICT low < level fill), D0 exit
from the actual fill price, maker 0.0002 / taker 0.00055, funding 0.0001 on
settling timeouts, stop-first priority. Copy of oc_b1deeper/oc_venuegap
logic plus a tp-scale hook (tp(d) = tp*(1-d/1e4)) and max-high miss.
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
OFFSETS = (1, 2, 3, 5)


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
                      o2: float, settle: bool, tp_scale: float = 1.0):
    """D0 replica from the actual fill price px. Returns (ret, x, how).

    tp_scale multiplies the TP leg only (tp(d) = tp*(1-d/1e4)); sl/bl
    unchanged. Same stop-first priority as oc_b1deeper/oc_venuegap.
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg) * float(tp_scale)
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


def max_high_miss_bps(Ha, f: int, tp: float) -> float:
    """(tp - max_high(f+1..239))/tp*1e4. Positive = shortfall; NaN if empty."""
    h = np.asarray(Ha[f + 1:240], dtype=float)
    h = h[np.isfinite(h)]
    if len(h) == 0 or not np.isfinite(tp) or tp <= 0:
        return float("nan")
    return float((tp - float(h.max())) / tp * 1e4)


def tp_for(px: float, sg: float, offset_bps: float) -> float:
    """TP leg with an inside offset: tp*(1-d/1e4)."""
    return px * (1 + 1.0 * sg) * (1 - float(offset_bps) / 1e4)
