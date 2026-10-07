"""oc_usdtdip core: D0 outcome + B1 n/size/fill + USDT tilt helpers. Pure numpy, no I/O.

D0 outcome_mu is a verbatim reuse of research/tournament/oc_dipexit/exits.py
(TP 1 sigma, close5 stop 4 sigma, 8-sigma backstop, timeout at next-bar open;
maker 0.0002 / taker 0.00055; v293 settle funding on timeouts). n/size/fill
are a verbatim reuse of research/tournament/oc_b1deeper/deeper.py (static
level variant). USDT z math mirrors oc_usdtprem (mean24 + trailing-90d z).
See PLAN.md for frozen definitions.
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
Z_HI = 1.0
Z_LO = -1.0
MULT_UP = 1.2
MULT_DOWN = 0.8
NS = 1_000_000_000


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


def tilt_mult(z: float) -> float:
    """Fixed size tilt from the USDT z-score (NaN -> 1.0, never tilted)."""
    if not np.isfinite(z):
        return 1.0
    if z > Z_HI:
        return MULT_UP
    if z < Z_LO:
        return MULT_DOWN
    return 1.0


def asof_index(ends_ns: np.ndarray, Tns: np.ndarray) -> np.ndarray:
    """For each bar open T (ns), index of last USDT row with end <= T - 1s.

    -1 where no row qualifies (warm-up). Strictly-before-T by construction.
    """
    return np.searchsorted(ends_ns, Tns - NS, side="left") - 1
