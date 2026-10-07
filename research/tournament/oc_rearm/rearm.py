"""oc_rearm core: vendored oc_b1deeper B1/D0 core + re-arm search + G=2.0 cap walk.

Pure numpy, no I/O. Base/exit definitions frozen in PLAN.md (idea #67) and
bit-identical to research/tournament/oc_b1deeper/deeper.py.
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the timeout exit is at a settling bar open.
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
GROSS_CAP = 2.0
CAP_EPS = 1e-12


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
    """B1 size multiplier: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level_win: np.ndarray):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < np.asarray(level_win, dtype=float)
    if hit.any():
        return int(np.argmax(hit))
    return None


def find_refill(low_win: np.ndarray, level: float, start_idx: int):
    """First live-window index i >= start_idx with low[i] < level (STRICT).

    The re-armed bid rests from the minute after the TP exit; start_idx is
    the live-window index of that minute. Returns int index or None.
    NaN lows never fill.
    """
    lo = np.asarray(low_win, dtype=float)
    if start_idx >= len(lo):
        return None
    seg = lo[start_idx:] < float(level)
    if seg.any():
        return int(start_idx + np.argmax(seg))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the fill price px.

    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open);
    how in {"tp","stop","backstop","time"}. NaN ret when exit price missing.
    Priority stop-first (same as oc_dipexit D0 / v293 / oc_b1deeper).
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


def gross_cap_weights(f, x, w, order, G=GROSS_CAP, parent=None):
    """Engine `sleeve_gross_cap` walk: cut each new rung to the room left.

    f/x/w: parallel sequences (fill offset, exit offset, size) of one
    (phase, bar) candidate pool. order: positions in processing order
    ((f ASC, k ASC, coin ASC); a re-armed fill always sorts after its
    parent since f2 > f). parent: optional parallel sequence with the
    position of the parent base fill, or -1/None for base fills; a
    re-armed candidate whose parent kept 0.0 is dropped (no position,
    hence no TP) without consuming room. Returns dict pos -> w_kept
    (0.0 = skipped). Open at f = kept fills with exit x > f (an exit at
    minute <= f is observably closed by f). Skipped fills never open.
    """
    kept = {}
    open_fills = []  # (x_exit, w_kept) of kept fills so far
    for p in order:
        if parent is not None and parent[p] is not None and parent[p] >= 0:
            if kept.get(parent[p], 0.0) <= 0.0:
                kept[p] = 0.0
                continue
        fi, xi, wi = int(f[p]), int(x[p]), float(w[p])
        open_w = sum(wk for (xk, wk) in open_fills if xk > fi)
        room = float(G) - open_w
        if room <= CAP_EPS:
            kept[p] = 0.0
        else:
            wk = wi if wi <= room else room
            kept[p] = wk
            open_fills.append((xi, wk))
    return kept
