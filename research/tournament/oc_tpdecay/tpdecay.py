"""oc_tpdecay core: B1 fill + BASE (fixed TP) vs DECAY (time-decaying TP) exits.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #54).
Rung replica = oc_b1deeper B1: static bid at lv, fill on strict low < lv,
size 1/(1+n_fill). D0 exits from the fill price px except the TP leg.
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the exit is at a settling bar open
(timeout, or close5-stop at minute 240).
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


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W).

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) sg_b(T).
    Returns int array (W,) with values 0..4. NaN open/sigma/close -> no
    detection (conservative). Flush at exactly 2.5 sigma counts (<=).
    """
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
    """B1 size multiplier, both arms: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def tp_decay_level(px: float, sg: float, f: int, t: int) -> float:
    """Decaying TP level in force at post-fill minute t.

    TP(t) = px * (1 + sg * (1.0 - 0.5*(t-f)/(240-f))).
    Uses only px, sg, f (known at the fill minute). t in f+1..239.
    """
    return float(px) * (1 + float(sg) * (1.0 - 0.5 * (int(t) - int(f)) / (240 - int(f))))


def tp_decay_vector(px: float, sg: float, f: int, t0: int, t1: int) -> np.ndarray:
    """TP(t) for t in [t0, t1) as a float array. Pure function of px/sg/f."""
    t = np.arange(t0, t1, dtype=float)
    return np.asarray(px, dtype=float) * (1 + float(sg) * (1.0 - 0.5 * (t - float(f)) / (240 - float(f))))


def outcome_base(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle: bool):
    """D0 replica with FIXED TP = px*(1+sg). Returns (ret, x, how)."""
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
        fill_px = bl if ox > bl else ox  # min(bl, open): gap pays the open
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


def outcome_decay(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                  o2: float, settle: bool):
    """D0 replica with DECAYING TP(t) = px*(1+sg*(1-0.5*(t-f)/(240-f))).

    Stops, backstop, timeout identical to outcome_base. TP touch: first t
    with high(t) > TP(t) (STRICT, time-varying); exit at TP(t) maker.
    Priority stop-first identical to base.
    Returns (ret, x, how, tp_px) with tp_px = exit TP level on tp else NaN.
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    Hwin = np.asarray(Ha[f + 1:240], dtype=float)
    tpv = tp_decay_vector(px, sg, f, f + 1, 240)
    # NaN highs never touch (NaN > x is False); NaN TP would also not touch.
    ht = np.isfinite(Hwin) & np.isfinite(tpv) & (Hwin > tpv)
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop", float("nan"))
        fill_px = bl if ox > bl else ox
        return (fill_px / px - 1 - MAKER - TAKER, x, "backstop", float("nan"))
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        tp = float(tpv[kt])
        return (tp / px - 1 - 2 * MAKER, x, "tp", tp)
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            ex, x = float(Oa[km + 1]), km + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "stop", float("nan"))
        ret = ex / px - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop", float("nan"))
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time", float("nan"))
    return (float(o2) / px - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time", float("nan"))
