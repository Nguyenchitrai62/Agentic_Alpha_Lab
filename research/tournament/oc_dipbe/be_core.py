"""oc_dipbe core: B1 rung replica (copied from oc_b1deeper/deeper.py) + BE exit.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #34).
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the exit at offset 240 is at a settling bar open.
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
BE_TRIG_K = 0.6


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W), v399-exact."""
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


def find_fill(low_win: np.ndarray, level_win: np.ndarray):
    """First offset index into the live window with low < level (STRICT)."""
    hit = np.asarray(low_win, dtype=float) < np.asarray(level_win, dtype=float)
    if hit.any():
        return int(np.argmax(hit))
    return None


def _first(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_base(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle: bool):
    """D0 replica from fill price px (oc_b1deeper-exact). Returns (ret, x, how)."""
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = _first(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = _first(ht)
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


def outcome_be(Ha, La, Ca, Oa, f: int, px: float, sg: float,
               o2: float, settle: bool):
    """Break-even arm (PLAN #34): after high > px*(1+0.6sg), close-stop -> px*(1+MAKER+TAKER).

    Arms only if the trigger minute tb is strictly before every base trigger;
    ties go to the base exit. Returns (ret, x, how, armed).
    """
    be_trig = px * (1 + BE_TRIG_K * sg)
    be_stop = px * (1 + MAKER + TAKER)
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    H = np.asarray(Ha[f + 1:240], dtype=float)
    L = np.asarray(La[f + 1:240], dtype=float)
    C = np.asarray(Ca[f + 1:240], dtype=float)
    O = np.asarray(Oa[f + 1:240], dtype=float)
    post = np.arange(f + 1, 240)
    is_clock = ((post + 1) % 5 == 0)
    kb = _first(L <= bl)
    kt = _first(H > tp)
    ks0 = _first(is_clock & (C <= sl))
    tb = _first(H > be_trig)
    armed = (tb is not None
             and (kt is None or tb < kt)
             and (kb is None or tb < kb)
             and (ks0 is None or tb < ks0))
    if not armed:
        ret, x, how = outcome_base(Ha, La, Ca, Oa, f, px, sg, o2, settle)
        return (ret, x, how, False)
    post_tb = post[tb + 1:]
    ks_be = None
    if len(post_tb):
        m = _first((((post_tb + 1) % 5 == 0)
                    & (np.asarray(Ca[f + 1 + tb + 1:240], dtype=float) <= be_stop)))
        ks_be = (tb + 1 + m) if m is not None else None
    if kb is not None and (ks_be is None or kb <= ks_be) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop", True)
        fill_px = bl if ox > bl else ox
        return (fill_px / px - 1 - MAKER - TAKER, x, "backstop", True)
    if kt is not None and (ks_be is None or kt < ks_be):
        x = f + 1 + kt
        return (tp / px - 1 - 2 * MAKER, x, "tp", True)
    if ks_be is not None:
        km = f + 1 + ks_be
        if km + 1 < 240:
            ex, x = float(Oa[km + 1]), km + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "stop", True)
        ret = ex / px - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop", True)
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time", True)
    return (float(o2) / px - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time", True)
