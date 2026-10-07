"""oc_velocity core: correlation count, velocity guard, strict fill, D0 exit.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #23).
n / fill / exit logic is the oc_b1deeper deeper.py replica (B1 size-only,
D0-from-fill exits); guard_trigger is new. Costs: maker 0.0002 (fill + TP
legs), taker 0.00055 (stop/backstop/time legs). Funding: longs pay 0.0001
when the timeout exit is at a settling bar open.
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
VEL_K = 3.0
VEL_SPAN = 16  # closes c[m-16..m-1] per decision minute m


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W).

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) sg_b(T).
    Returns int array (W,) with values 0..4. NaN open/sigma/close -> no
    detection (conservative). Flush at exactly 2.5 sigma counts (<=).
    (Replica of oc_b1deeper deeper.n_vector.)
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
    """B1 size multiplier kept for both arms: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level_win: np.ndarray):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < np.asarray(level_win, dtype=float)
    if hit.any():
        return int(np.argmax(hit))
    return None


def guard_minute(btc_closes_240: np.ndarray, sg_btc: float):
    """First live minute m* with a 3-sigma 15-min velocity drop, or None.

    btc_closes_240: float array length >= 240, c[i] = BTC 1m close at
      bar-relative minute i (0..239). sg_btc: sg_BTC(T) known at bar open.
    For m in [16..238]: window W(m) = c[m-16..m-1] (16 closes, all closed
    by minute T+m-1, hence causal for minute-m trading). Triggers iff all
    16 are finite AND c[m-1] <= max(W(m)) * (1 - 3*sg). Returns smallest
    such m, else None. Non-finite/non-positive sg -> None.
    """
    try:
        sg = float(sg_btc)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(sg) and sg > 0):
        return None
    c = np.asarray(btc_closes_240, dtype=float)
    if c.shape[0] < LIVE_B + 1:
        return None
    factor = 1.0 - VEL_K * sg
    if not np.isfinite(factor):
        return None
    for m in range(LIVE_A, LIVE_B + 1):
        win = c[m - VEL_SPAN:m]
        if win.shape[0] != VEL_SPAN:
            continue
        if not np.all(np.isfinite(win)):
            continue
        cur = float(win[-1])  # c[m-1]
        mx = float(np.max(win))
        if not (np.isfinite(cur) and np.isfinite(mx)):
            continue
        if cur <= mx * factor:
            return int(m)
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the fill price px.

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first (same as oc_dipexit D0 / oc_b1deeper).
    (Replica of oc_b1deeper deeper.outcome_from_fill.)
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
