"""oc_b1soft core: soft correlation count, strict fill, D0-from-fill exit.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #24).
Exit replica is byte-identical in logic to oc_b1deeper deeper.py
outcome_from_fill (same fees/funding/priority); all four arms share the
same static-bid fills, only weights differ.

Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time).
Funding: longs pay 0.0001 when the timeout exit is at a settling bar open.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP, TP_K = 4.0, 8.0, 1.0
SOFT_LO, SOFT_HI = 1.0, 2.5
ARMS_F = (2.5, 2.0, 1.5)


def d_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Flush distance per other major: (O - C)/(O*sg), NaN where invalid.

    close_others/open_others/sigma_others: (4,) arrays at the fill minute
    (C = close at T+f-1). Non-finite O, non-finite sg, sg <= 0, O <= 0,
    or non-finite C -> NaN (contributes 0 downstream).
    """
    c = np.asarray(close_others, dtype=float)
    o = np.asarray(open_others, dtype=float)
    sg = np.asarray(sigma_others, dtype=float)
    d = np.full(c.shape, np.nan, dtype=float)
    ok = (np.isfinite(c) & np.isfinite(o) & np.isfinite(sg)
          & (o > 0) & (sg > 0))
    d[ok] = (o[ok] - c[ok]) / (o[ok] * sg[ok])
    return d


def n_hard_from_d(d: np.ndarray, f: float) -> int:
    """Hard count #{d_b >= F}; NaN never counts; exact boundary counts."""
    d = np.asarray(d, dtype=float)
    return int((np.isfinite(d) & (d >= float(f))).sum())


def n_soft_from_d(d: np.ndarray) -> float:
    """Soft count sum_b clip((d_b-1)/1.5, 0, 1); NaN -> 0. Range 0..4."""
    d = np.asarray(d, dtype=float)
    v = (d - SOFT_LO) / (SOFT_HI - SOFT_LO)
    v = np.clip(v, 0.0, 1.0)
    v[~np.isfinite(v)] = 0.0
    return float(v.sum())


def n_hard_vector(close_others: np.ndarray, open_others: np.ndarray,
                  sigma_others: np.ndarray, f: float) -> np.ndarray:
    """Hard count per live minute (vector length W), v399-exact.

    close_others: (4, W) closes at T+m-1. Used only for tests/cross-checks.
    """
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - float(f) * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def size_mult(n) -> float:
    """B1 size multiplier 1/(1+n); accepts int or float (soft)."""
    return 1.0 / (1.0 + float(n))


def find_fill(low_win: np.ndarray, level_win: np.ndarray):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < np.asarray(level_win, dtype=float)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the fill price px (here px = lv).

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first (same as oc_b1deeper D0 / v293 / oc_dipexit).
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + TP_K * sg)
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
