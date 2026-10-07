"""oc_discsniper core: premium-z trigger, limit fill, stop/premium/timeout race.

Pure numpy, no I/O. Definitions frozen in PLAN.md.
Costs: fill maker 0.0002; premium exit maker 0.0002; stop/timeout taker 0.00055.
Funding: longs pay 0.0001 per 8h settlement held (00/08/16 UTC).
Dip replica (D0 + B1) is copied exact from oc_b1deeper/oc_placebo_dip (no import).
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
Z_THRESH = -2.0
ENTRY_OFF = 0.001
LIVE_A, LIVE_B = 5, 59  # valid 60 min, fills banned in first 5 min
M_SL = 4.0
SIZE = 0.25
P15_WIN = 15
TRAIL_WIN = 1440
TRAIL_MIN = 1200

# dip replica constants (oc_b1deeper-exact)
DIP_RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
DIP_LIVE_A, DIP_LIVE_B = 16, 238
DIP_M_SL, DIP_BACKSTOP = 4.0, 8.0
DIP_DETECT_K = 2.5


def p15_from_close(prem_close: np.ndarray) -> np.ndarray:
    """15-min mean premium per minute; NaN if any of the 15 closes non-finite."""
    x = np.asarray(prem_close, dtype=float)
    n = len(x)
    out = np.full(n, np.nan)
    if n < P15_WIN:
        return out
    finite = np.isfinite(x)
    # window all-finite check via cumsum
    cs = np.concatenate([[0], np.cumsum(finite.astype(np.int64))])
    cnt = cs[P15_WIN:] - cs[:-P15_WIN]
    csum = np.concatenate([[0.0], np.cumsum(np.where(finite, x, 0.0))])
    s = csum[P15_WIN:] - csum[:-P15_WIN]
    vals = np.where(cnt == P15_WIN, s / P15_WIN, np.nan)
    out[P15_WIN - 1:] = vals
    return out


def z_from_p15(p15: np.ndarray, i: int) -> float:
    """z at bar with minute index i (bar open minute). Uses only minutes < i.

    cur = p15[i-1]; trailing = p15[i-1441:i-1] (1440 values, current excluded).
    """
    if i < 1:
        return np.nan
    cur = float(p15[i - 1]) if (i - 1) < len(p15) else np.nan
    if not np.isfinite(cur):
        return np.nan
    lo = i - 1 - TRAIL_WIN
    hi = i - 1
    if lo < 0:
        return np.nan
    tr = np.asarray(p15[lo:hi], dtype=float)
    fin = tr[np.isfinite(tr)]
    if len(fin) < TRAIL_MIN:
        return np.nan
    sd = float(np.std(fin, ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return np.nan
    return (cur - float(np.mean(fin))) / sd


def find_fill_disc(low_win: np.ndarray, lim: float):
    """First live-window index with low < lim (STRICT). None if never."""
    hit = np.asarray(low_win, dtype=float) < float(lim)
    if hit.any():
        return int(np.argmax(hit))
    return None


def funding_count(t_fill: int, t_exit: int, settle_mask: np.ndarray) -> int:
    """Number of settlements s with t_fill < s <= t_exit (minute indices)."""
    if t_exit <= t_fill:
        return 0
    return int(np.count_nonzero(settle_mask[t_fill + 1:t_exit + 1]))


def outcome_disc(Hb, Lb, Cb, Ob, p15b, f: int, px: float, sg: float,
                 o2: float, t_fill_abs: int, t_bar_abs: int,
                 settle_mask: np.ndarray):
    """Disc-sniper exit race from fill. Arrays length 240 (offsets 0..239).

    Hb/Lb/Cb/Ob: 1m high/low/close/open at offsets 0..239 (float).
    p15b: p15 values at offsets 0..239 (p15 at minute T+m).
    f: fill offset (5..59). px: fill price. sg: sigma. o2: next-bar open.
    Returns (ret, x, how) with x in 1..240 (240 = timeout at next open),
    how in {"stop","premium","time"}. NaN ret when exit open missing.
    """
    sl = px * (1 - M_SL * sg)
    # stop trigger minutes (bar-relative (m+1)%5==0, T%5==0 so = clock grid)
    ms = None
    for m in range(f + 1, 240):
        if (m + 1) % 5 != 0:
            continue
        c = float(Cb[m]) if m < len(Cb) else np.nan
        if np.isfinite(c) and c <= sl:
            ms = m
            break
    # premium trigger minutes
    mp = None
    for m in range(f + 1, 240):
        v = float(p15b[m]) if m < len(p15b) else np.nan
        if np.isfinite(v) and v >= 0:
            mp = m
            break
    if ms is not None and (mp is None or ms <= mp):
        x = ms + 1
        if x < 240:
            ex = float(Ob[x])
            if not np.isfinite(ex):
                return (np.nan, x, "stop")
        else:
            ex = float(o2)
            if not np.isfinite(ex):
                return (np.nan, 240, "stop")
            x = 240
        t_exit_abs = t_bar_abs + x
        nset = funding_count(t_fill_abs, t_exit_abs, settle_mask)
        return (ex / px - 1 - MAKER - TAKER - FUND * nset, x, "stop")
    if mp is not None:
        x = mp + 1
        if x < 240:
            ex = float(Ob[x])
            if not np.isfinite(ex):
                return (np.nan, x, "premium")
        else:
            ex = float(o2)
            if not np.isfinite(ex):
                return (np.nan, 240, "premium")
            x = 240
        t_exit_abs = t_bar_abs + x
        nset = funding_count(t_fill_abs, t_exit_abs, settle_mask)
        return (ex / px - 1 - 2 * MAKER - FUND * nset, x, "premium")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    t_exit_abs = t_bar_abs + 240
    nset = funding_count(t_fill_abs, t_exit_abs, settle_mask)
    return (float(o2) / px - 1 - MAKER - TAKER - FUND * nset, x, "time")


# ---- dip replica (oc_b1deeper-exact) ----

def dip_n_vector(close_others: np.ndarray, open_others: np.ndarray,
                 sigma_others: np.ndarray) -> np.ndarray:
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DIP_DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def dip_size_mult(n_fill: int) -> float:
    return 1.0 / (1 + int(n_fill))


def dip_find_fill(low_win: np.ndarray, level: float):
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def dip_outcome(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                o2: float, settle: bool):
    sl = lv * (1 - DIP_M_SL * sg)
    bl = lv * (1 - DIP_BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
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
        return (fill_px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        return (tp / lv - 1 - 2 * MAKER, f + 1 + kt, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            ex, x = float(Oa[km + 1]), km + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "stop")
        ret = ex / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    return (float(o2) / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time")
