"""oc_expirydip core: expiry calendar + exact oc_dipexit D0 / oc_b1deeper B1 replica.

Pure numpy, no I/O (see run.py). Definitions frozen in PLAN.md.
Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 when the timeout exit is at a settling bar open.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
EXTRA_K = 5.0
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5


# --------------------------------------------------------------------------
# expiry calendar (pure function of year/month, no market input)
# --------------------------------------------------------------------------
def last_friday(y: int, m: int) -> int:
    """Day-of-month of the last Friday of month m."""
    last_day = calendar.monthrange(y, m)[1]
    wd = calendar.weekday(y, m, last_day)  # Monday == 0 .. Sunday == 6
    back = (wd - 4) % 7  # Friday == 4
    return last_day - back


def expiry_dates(y0: int = 2021, y1: int = 2026, m1: int = 9) -> set:
    """Set of datetime.date expiry dates from (y0,1) through (y1,m1) inclusive."""
    out = set()
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            if y == y1 and m > m1:
                break
            if y == y0 and m < 1:
                continue
            import datetime as _dt
            out.add(_dt.date(y, m, last_friday(y, m)))
    return out


def in_exp_window(ts: pd.Timestamp, expiries: set) -> bool:
    """True iff ts falls on an expiry date with time in [00:00, 12:00) UTC.

    Phase-0 bars opening 00:00/04:00/08:00 qualify; shifted phases qualify
    the 3 bars opening inside the same 12h window. Pure timestamp logic.
    """
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    if t.date() not in expiries:
        return False
    mins = t.hour * 60 + t.minute
    return 0 <= mins < 12 * 60


# --------------------------------------------------------------------------
# replica core (oc_dipexit outcome_mu + oc_b1deeper n/size/fill)
# --------------------------------------------------------------------------
def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


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


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """oc_dipexit-exact long rung outcome for TP multiple mu.

    Returns (ret, x, how); x = exit offset (240 = next-bar open).
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
