"""oc_dipexit exits core: v293 replica (long dip ladder) + E1-E4 exact outcomes.

Pure numpy on 1m slices; no I/O here (see run.py). All definitions match PLAN.md.
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the timeout exit is at a settling bar open
((bar_open+4h).hour in (0,8,16)); intrabar exits pay no funding.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """Replica of v293 outcomes() for one TP multiple. Returns (ret, x, how).

    x = exit offset (0..239 inside the bar, 240 = next-bar open).
    how in {"tp","stop","backstop","time"}. NaN ret when the exit price is missing.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (Ca[f + 1:240] <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La[f + 1:240] <= bl
    kb = _first_idx(hb)
    ht = Ha[f + 1:240] > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox  # min(bl, open): gap down pays the open
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px = Oa[km + 1]
            x = km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    ret = o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0)
    return (ret, x, "time")


def outcome_e2(Ha, La, Ca, Oa, f: int, lv: float, sg: float, o2: float, settle: bool):
    """E2: TP 1 sigma + forced time exit at open(f+120). Returns (ret, x, how)."""
    d = f + 120
    if d >= 240:
        ret, x, how = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 1.0, o2, settle)
        return (ret, x, "time" if how == "time" else how)
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    post = np.arange(f + 1, d)
    trig = (Ca[f + 1:d] <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La[f + 1:d] <= bl
    kb = _first_idx(hb)
    ht = Ha[f + 1:d] > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        px, x = Oa[km + 1], km + 1  # km+1 <= d < 240 here
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        return (px / lv - 1 - MAKER - TAKER, x, "stop")
    x = d
    px = Oa[d]
    if not np.isfinite(px):
        return (np.nan, x, "time")
    return (px / lv - 1 - MAKER - TAKER, x, "time")  # intrabar: no funding


def outcome_e3(Ha, La, Ca, Oa, f: int, lv: float, sg: float, o2: float, settle: bool):
    """E3: TP 1 sigma; after +0.5-sigma touch the close5 stop moves to breakeven."""
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    act = lv * (1 + 0.5 * sg)
    ha = Ha[f + 1:240] > act
    ka = None if not ha.any() else f + 1 + int(np.argmax(ha))
    post = np.arange(f + 1, 240)
    is_clock = ((post + 1) % 5 == 0)
    if ka is None:
        thr = np.full(post.shape, sl)
    else:
        thr = np.where(post <= ka, sl, lv)
    trig = is_clock & (Ca[f + 1:240] <= thr)
    ks = _first_idx(trig)
    hb = La[f + 1:240] <= bl
    kb = _first_idx(hb)
    ht = Ha[f + 1:240] > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = Oa[km + 1], km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")


def outcome_e4(Ha, La, Ca, Oa, f: int, lv: float, sg: float, o1: float,
               o2: float, settle: bool):
    """E4: TP = min(bar open, lv*(1+2*sigma)); same race as the replica."""
    tp = o1 if o1 < lv * (1 + 2.0 * sg) else lv * (1 + 2.0 * sg)
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    post = np.arange(f + 1, 240)
    trig = (Ca[f + 1:240] <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La[f + 1:240] <= bl
    kb = _first_idx(hb)
    ht = Ha[f + 1:240] > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = Oa[km + 1], km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")
