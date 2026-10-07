"""oc_depthtilt core: vendored B1/D0 replica + depth tilt + v421-style G-cap walk.

Pure numpy, no I/O. Definitions frozen in PLAN.md (idea #78).
Bit-identical constants to oc_b1deeper/deeper.py and oc_bidttl/bidttl.py:
costs maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs);
funding: longs pay 0.0001 when the timeout exit is at a settling bar open
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
GROSS_CAP = 2.0
CAP_EPS = 1e-12

# Frozen depth tilt: raw(k) = k/2.5, renormalised so sum over the ladder = 5.0
# (ex-ante exposure neutral per coin-bar). sum(raw) = 7.2.
_TILT_RAW = {2.5: 1.0, 3.0: 1.2, 3.5: 1.4, 4.0: 1.6, 5.0: 2.0}
_TILT_SUM = sum(_TILT_RAW.values())  # 7.2
TILT = {k: v / _TILT_SUM * 5.0 for k, v in _TILT_RAW.items()}


def tilt_mult(k: float) -> float:
    """Nominal depth-tilt multiplier for rung k (B1 factor applied on top)."""
    return float(TILT[float(k)])


def rule_weight(n_fill: int, k: float) -> float:
    """Depth-tilted weight: B1 size x tilt = tilt(k)/(1+n_fill)."""
    return tilt_mult(k) / (1 + int(n_fill))


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


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if never.

    NaN lows never fill (NaN < x is False).
    """
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_from_fill(Ha, La, Ca, Oa, f: int, px: float, sg: float,
                      o2: float, settle: bool):
    """D0 replica measured from the fill price px (= lv here).

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


def gross_cap_weights(f, x, w, order, G=GROSS_CAP):
    """Engine `sleeve_gross_cap` walk: cut each new rung to the room left.

    f/x/w: parallel sequences (fill offset, exit offset, size) of one
    (phase, bar) candidate pool. order: positions in processing order
    ((f ASC, k ASC, coin ASC)). Returns dict pos -> w_kept (0.0 = skipped).
    Open at f = kept fills with exit x > f (an exit at minute <= f is
    observably closed by f). Skipped fills never open. oc_rearm-exact.
    """
    kept = {}
    open_fills = []  # (x_exit, w_kept) of kept fills so far
    for p in order:
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


def exit_day_iso(t_bar, x: int) -> str:
    """Calendar UTC exit date ISO for a fill of bar t_bar with exit offset x."""
    import pandas as pd

    if int(x) < 240:
        return (t_bar + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (t_bar + pd.Timedelta(hours=4)).date().isoformat()


def cell_stats_dict(dates, wy):
    """(S, worst_day, maxDD, ndays) of daily sums. DD >= 0 in w*y units."""
    import numpy as np

    dates = np.asarray(dates)
    wy = np.asarray(wy, dtype=float)
    if wy.size == 0:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in zip(dates.tolist(), wy.tolist()):
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)
