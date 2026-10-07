"""oc_outage core: D0 outcome + B1 helpers + outage overlay. Pure numpy, no I/O.

D0 outcome_mu is a verbatim reuse of research/tournament/oc_dipexit/exits.py
(TP 1 sigma, close5 stop 4 sigma, 8-sigma backstop, timeout at next-bar open;
maker 0.0002 / taker 0.00055; v293 settle funding on timeouts). B1 n/size are
a verbatim reuse of research/tournament/oc_b1deeper/deeper.py (static level).
Outage intervals use absolute-minute coordinates (minutes since START =
2020-08-01 00:00 UTC); see PLAN.md for frozen definitions.
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
SETTLE_HOURS = (0, 8, 16)


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """oc_dipexit-exact long rung outcome for TP multiple mu.

    Returns (ret, x, how); x = exit offset (240 = next-bar open).
    Priority stop-first (v293): backstop wins ties; else TP wins only if
    strictly earlier; else stop; else timeout. Same-minute stop+TP -> stop.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
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


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """v399-exact correlation count per live minute (0..4). NaN -> no detect."""
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


# ---------------------------------------------------------------------------
# Outage intervals (absolute-minute coordinates, minutes since START)
# ---------------------------------------------------------------------------

def is_offline(m: int, intervals) -> bool:
    """True iff absolute minute m lies in any [s, e) interval (sorted)."""
    for s, e in intervals:
        if m < s:
            return False
        if m < e:
            return True
    return False


def comeback(m: int, intervals):
    """First online absolute minute >= m (m itself when online)."""
    for s, e in intervals:
        if m < s:
            return m
        if m < e:
            return e
    return m


def gen_block_outages(year_abs: int, block_len: int, dur: int, seed: int):
    """One outage per block: blocks tile [year_abs, year_abs+525600).

    block_len/dur in minutes. Returns sorted [(s, e)] absolute minutes.
    Start offsets uniform in [0, block_len-dur] via default_rng(seed),
    in block order. The weekly case (52x10080m = 524160m) leaves the
    1440m tail outage-free by construction (disclosed in PLAN.md).
    """
    rng = np.random.default_rng(seed)
    n = 525600 // block_len
    out = []
    for b in range(n):
        lo = year_abs + b * block_len
        span = block_len - dur
        off = int(rng.integers(0, span + 1))
        out.append((lo + off, lo + off + dur))
    return sorted(out)


def rank_worst_hours(hour_abs: np.ndarray, mean_ret: np.ndarray, k: int = 10):
    """Indices (into hour_abs) of the k lowest finite mean returns.

    NaN hours never rank. Ties broken by earliest hour (stable argsort).
    """
    ok = np.isfinite(mean_ret)
    idx = np.where(ok)[0]
    order = idx[np.argsort(mean_ret[idx], kind="stable")]
    return order[:k].tolist()


# ---------------------------------------------------------------------------
# Deferred exit under outage (PLAN.md formal rule)
# ---------------------------------------------------------------------------

def apply_outage_to_fill(f: int, lv: float, sg: float,
                          base_ret: float, base_x: int, base_how: str,
                          t_abs: int, o2: float, settle: bool,
                          H, L, O, intervals):
    """Apply the outage overlay to one kept fill.

    H/L/O are full-coin 1m arrays indexed by absolute minute (float; NaN =
    missing). intervals is a sorted list of (s, e) absolute minutes.
    Returns (ret, x_off, how, delayed, rescued) where x_off is the scenario
    exit offset (may exceed 240 when the comeback is past the bar end),
    how in {"tp","backstop","stop","time","stop_late","time_late","dropped"},
    delayed = base stop/time deferred, rescued = a native TP/backstop fired
    during the delay window before the comeback.
    """
    te = t_abs + int(base_x)
    if base_how in ("tp", "backstop"):
        return (float(base_ret), int(base_x), base_how, False, False)
    if not is_offline(te, intervals):
        return (float(base_ret), int(base_x), base_how, False, False)
    ce = comeback(te, intervals)
    tp = lv * (1 + 1.0 * sg)
    bl = lv * (1 - BACKSTOP * sg)
    # native touches in [f+1, ce-t_abs) as absolute minutes
    best_tp = None
    best_bl = None
    start = t_abs + int(f) + 1
    for m in range(start, ce):
        off = m - t_abs
        if off < 0:
            continue
        if m < 0 or m >= len(H):
            continue
        h = H[m]
        lo = L[m]
        if np.isfinite(h) and h > tp and best_tp is None:
            best_tp = m
        if np.isfinite(lo) and lo <= bl and best_bl is None:
            best_bl = m
        if best_tp is not None and best_bl is not None:
            break
    if best_bl is not None and (best_tp is None or best_bl <= best_tp):
        ox = O[best_bl]
        if not np.isfinite(ox):
            return (np.nan, int(best_bl - t_abs), "dropped", True, False)
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, int(best_bl - t_abs),
                "backstop", True, True)
    if best_tp is not None:
        return (tp / lv - 1 - 2 * MAKER, int(best_tp - t_abs),
                "tp", True, True)
    ox = O[ce] if 0 <= ce < len(O) else np.nan
    if not np.isfinite(ox):
        return (np.nan, int(ce - t_abs), "dropped", True, False)
    ret = ox / lv - 1 - MAKER - TAKER
    if settle and (ce - t_abs) >= 240:
        ret -= FUND
    late = "stop_late" if base_how == "stop" else "time_late"
    return (ret, int(ce - t_abs), late, True, False)


def cell_stats(dates: np.ndarray, wy: np.ndarray):
    """Exit-date daily sums -> (sum, worst_day, maxDD). Empty -> zeros."""
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    v = wy[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    return float(daily.sum()), float(daily.min()), float(-np.min(cum - peak))
