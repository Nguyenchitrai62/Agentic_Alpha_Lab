"""oc_fillttl core: B1 sizing + D0 replica + fill-relative T240/T120 outcomes.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #68).
D0 is the exact replica of oc_dipexit PLAN.md D0 (v293 Asset/outcomes).
T240/T120 keep sl/bl/tp and stop-first priority, only the time exit moves
to fill-relative offsets. Costs: maker 0.0002 (fill + TP), taker 0.00055
(stop/backstop/time). Funding: longs pay 0.0001 per 00/08/16 UTC settlement
in (t_fill, t_exit] when the exit is via TIME; 0 otherwise.
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
    Returns int array (W,) with values 0..4. NaN -> no detection.
    Flush at exactly 2.5 sigma counts (<=). v399/oc_b1deeper-exact.
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
    """First index into the live window with low < level (STRICT).

    Returns int index or None. NaN lows never fill.
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_d0(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
               o2: float, settle: bool):
    """Exact replica of oc_dipexit outcome_mu (D0, mu=1.0).

    Ha/La/Ca/Oa are length-240 bar slices (offsets 0..239).
    Returns (ret, x, how); x = exit offset (0..239, 240 = next-bar open).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
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
            px, x = float(Oa[km + 1]), km + 1
        else:
            px, x = float(o2), 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    ret = float(o2) / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0)
    return (ret, x, "time")


def outcome_fillrel(H, L, C, O, base: int, f: int, lv: float, sg: float,
                    x_time: int, n_settle: int):
    """Fill-relative time exit (T240/T120 core).

    H/L/C/O are FULL-length 1m arrays (float); base = bar-start global idx;
    f = fill offset (16..238); lv/sg = rung level and bar sigma;
    x_time = time-exit offset relative to bar start (240..478);
    n_settle = # of 00/08/16 UTC settlements in (t_fill, t_exit] (0..2),
    charged only when the exit is via TIME.
    Signals on t in f+1..x_time-1; close5 clock (t+1)%5==0 (bar-relative,
    == global 5-min clock since base%5==0 for all phases). Stop-first
    priority identical to D0. Returns (ret, x, how).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    if x_time <= f + 1:
        px = float(O[base + x_time]) if base + x_time < len(O) else np.nan
        if not np.isfinite(px):
            return (np.nan, x_time, "time")
        return (px / lv - 1 - MAKER - TAKER - FUND * int(n_settle),
                x_time, "time")
    post = np.arange(f + 1, x_time)
    n = x_time - f - 1
    Ca = np.asarray(C[base + f + 1:base + x_time], dtype=float)
    La = np.asarray(L[base + f + 1:base + x_time], dtype=float)
    Ha = np.asarray(H[base + f + 1:base + x_time], dtype=float)
    if not (len(Ca) == len(La) == len(Ha) == n):
        return (np.nan, x_time, "time")
    trig = (Ca <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La <= bl
    kb = _first_idx(hb)
    ht = Ha > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(O[base + x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        x = km + 1  # km+1 <= x_time by construction (km <= x_time-2 or == x_time-1)
        if x > x_time:
            x = x_time
        px = float(O[base + x])
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        # stop at the time minute coincides with the time price but pays no
        # funding (stop-first: stop wins the tie).
        return (px / lv - 1 - MAKER - TAKER, x, "stop")
    x = x_time
    if base + x >= len(O):
        return (np.nan, x, "time")
    px = float(O[base + x])
    if not np.isfinite(px):
        return (np.nan, x, "time")
    return (px / lv - 1 - MAKER - TAKER - FUND * int(n_settle), x, "time")


def overlap_minutes(f: int, x: int) -> int:
    """Minutes of [f+1, x) overlapping next-bar live window [256, 479).

    Held = x - f; overlap = intersection size. D0 (x<=240) gives 0.
    """
    lo = max(int(f) + 1, 256)
    hi = min(int(x), 479)
    return max(0, hi - lo)
