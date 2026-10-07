"""oc_stoptf core: B1 sizing + D0/S15/S1 stop-timeframe exact outcomes.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #72).
D0 = close5 stop (deployed, oc_dipexit replica); S15 = close15 stop;
S1 = every-1m-close stop. Stop LEVEL (4sg), backstop (8sg on 1m lows),
TP (1sg), timeout (next-bar open) unchanged; only the stop clock differs.
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
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """Correlation count per live minute (vector length W), v399-exact.

    close_others: (4, W) 1m closes at minutes T+m-1 for each other major.
    open_others: (4,) bar opens O_b(T). sigma_others: (4,) sg_b(T).
    Returns int array (W,) with values 0..4. NaN -> no detection.
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


def find_fill(low_win: np.ndarray, level: float):
    """First offset index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill.
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_stop_tf(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                    o2: float, settle: bool, clock: str):
    """Exact rung outcome with a given stop clock. Returns (ret, x, how).

    clock in {"close5", "close15", "close1"}. x = exit offset (0..239 inside
    the bar, 240 = next-bar open). how in {"tp","stop","backstop","time"}.
    NaN ret when the exit price is missing.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    Ca_seg = np.asarray(Ca[f + 1:240], dtype=float)
    if clock == "close5":
        is_clock = ((post + 1) % 5 == 0)
    elif clock == "close15":
        is_clock = ((post + 1) % 15 == 0)
    elif clock == "close1":
        is_clock = np.ones(post.shape, dtype=bool)
    else:
        raise ValueError(f"unknown clock {clock}")
    trig = is_clock & (Ca_seg <= sl)
    ks = _first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
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
