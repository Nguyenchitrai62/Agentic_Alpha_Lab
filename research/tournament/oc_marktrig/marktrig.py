"""oc_marktrig core: B1 n/size, BASE D0 exit, mark builder, MARK exit.

Pure numpy, no I/O. Definitions frozen in PLAN.md (IDEAS3 #6).
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the exit is at a settling next-bar open
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
DETECT_K = 2.5
PREM_WIN = 5


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W), v399/oc_b1deeper-exact."""
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
    """First live-window index with low < level (STRICT). None if never."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_base(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                 o2: float, settle: bool):
    """BASE = oc_dipexit D0 replica from fill price px. Returns (ret, x, how)."""
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


def build_mark(close_b: np.ndarray, prem_ext: np.ndarray) -> np.ndarray:
    """Reconstructed mark per bar offset 0..239.

    close_b: (240,) price 1m closes of the bar (float).
    prem_ext: (244,) premium 1m closes with prem_ext[4+t] = premium at
      bar offset t (4 leading minutes from before the bar; NaN if missing).
    mark[t] = close_b[t] * (1 + mean(finite prem_ext[t:t+5])).
    All-NaN window -> NaN mark (never triggers). Causal: only premium <= t.
    """
    cb = np.asarray(close_b, dtype=float)
    pe = np.asarray(prem_ext, dtype=float)
    assert cb.shape == (240,) and pe.shape == (240 + 4,)
    vals = np.where(np.isfinite(pe), pe, 0.0)
    msk = np.isfinite(pe).astype(float)
    csum = np.concatenate([[0.0], np.cumsum(vals)])
    ccnt = np.concatenate([[0.0], np.cumsum(msk)])
    tot = csum[5:245] - csum[0:240]
    cnt = ccnt[5:245] - ccnt[0:240]
    ma = np.where(cnt > 0, tot / np.where(cnt > 0, cnt, 1.0), np.nan)
    mark = cb * (1.0 + ma)
    mark[~(np.isfinite(cb) & np.isfinite(ma))] = np.nan
    return mark


def outcome_mark(Ha, La, Ca, Oa, mark_b: np.ndarray, f: int, px: float,
                 sg: float, o2: float, settle: bool):
    """MARK exit: TP/timeout identical to BASE; stops trigger on mark.

    mark_b: (240,) reconstructed marks of the bar (NaN never triggers).
    CLOSE5: first clock m in f+1..239 with (m+1)%5==0 and mark[m] <= sl,
      exit at open(m+1) (or o2 if m==239) taker.
    BACKSTOP: first t in f+1..239 with mark[t] <= bl, exit at open(t+1)
      (or o2 if t==239) taker (next-minute market; no min() cap).
    TP: first t with high(t) > tp STRICT, exit at tp 2*maker (unchanged).
    Priority stop-first (backstop ties, TP strictly earlier, else stop).
    Returns (ret, x, how).
    """
    sl = px * (1 - M_SL * sg)
    bl = px * (1 - BACKSTOP * sg)
    tp = px * (1 + 1.0 * sg)
    mb = np.asarray(mark_b, dtype=float)
    assert mb.shape == (240,)
    post = np.arange(f + 1, 240)
    mmark = mb[f + 1:240]
    trig = np.isfinite(mmark) & (mmark <= sl) & (((post + 1) % 5) == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    bmark = mb[f + 1:240]
    hb = np.isfinite(bmark) & (bmark <= bl)
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    Oa = np.asarray(Oa, dtype=float)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        t_trig = f + 1 + kb
        if t_trig + 1 < 240:
            ex, x = float(Oa[t_trig + 1]), t_trig + 1
        else:
            ex, x = float(o2), 240
        if not np.isfinite(ex):
            return (np.nan, x, "backstop")
        ret = ex / px - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / px - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        m_trig = f + 1 + ks
        if m_trig + 1 < 240:
            ex, x = float(Oa[m_trig + 1]), m_trig + 1
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
