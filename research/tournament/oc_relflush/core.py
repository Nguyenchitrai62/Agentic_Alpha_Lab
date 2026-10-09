"""oc_relflush core: D0 outcome + B1 n/size/fill + relative-flush tilt helpers.

Pure numpy, no I/O. D0 outcome_mu is a verbatim reuse of
research/tournament/oc_placebo_dip/compute_placebo_dip.py
(TP 1 sigma, close5 stop 4 sigma, 8-sigma backstop, timeout at next-bar open;
maker 0.0002 / taker 0.00055; v293 settle funding). n/size/fill are a verbatim
reuse of research/tournament/oc_b1deeper/deeper.py (static level variant).
rel/tilt helpers implement OPENCODE_W_oc_relflush.md (bot_only, minute f-1).
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
REL_HI = 0.5
REL_LO = -0.5
R1_UP = 1.5
R1_DOWN = 0.75
R3_SLOPE = 0.25
R3_LO = 0.6
R3_HI = 1.4


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


# --------------------------------------------------------------------------
# relative-flush helpers (bot_only, minute f-1 only)
# --------------------------------------------------------------------------

def depth_sigma(px_close: float, bar_open: float, sigma: float) -> float:
    """d_x = -log(P/O)/sigma. NaN if any leg missing/non-positive."""
    if not (np.isfinite(px_close) and np.isfinite(bar_open)
            and np.isfinite(sigma)):
        return float("nan")
    if bar_open <= 0 or px_close <= 0 or sigma <= 0:
        return float("nan")
    r = px_close / bar_open
    if not np.isfinite(r) or r <= 0:
        return float("nan")
    return float(-np.log(r) / sigma)


def rel_overshoot(d_own: float, d_flush: np.ndarray) -> float:
    """rel = d_i - mean(F). NaN if d_own NaN, F empty, or mean non-finite."""
    if not np.isfinite(d_own):
        return float("nan")
    arr = np.asarray(d_flush, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    m = float(arr.mean())
    if not np.isfinite(m):
        return float("nan")
    return float(d_own - m)


def tilt_r1(rel: float, n_fill: int) -> float:
    """R1 tilt: 1.5 if rel>+0.5; 0.75 if rel<-0.5; else 1. n=0 -> 1."""
    if int(n_fill) <= 0:
        return 1.0
    if not np.isfinite(rel):
        return 1.0
    if rel > REL_HI:
        return R1_UP
    if rel < REL_LO:
        return R1_DOWN
    return 1.0


def tilt_r2(rel: float, n_fill: int) -> float:
    """R2 sign control (mirror of R1). n=0 -> 1."""
    if int(n_fill) <= 0:
        return 1.0
    if not np.isfinite(rel):
        return 1.0
    if rel > REL_HI:
        return R1_DOWN
    if rel < REL_LO:
        return R1_UP
    return 1.0


def tilt_r3(rel: float, n_fill: int) -> float:
    """R3 smooth tilt: clip(1+0.25*rel, 0.6, 1.4). n=0 -> 1."""
    if int(n_fill) <= 0:
        return 1.0
    if not np.isfinite(rel):
        return 1.0
    v = 1.0 + R3_SLOPE * float(rel)
    if v < R3_LO:
        return R3_LO
    if v > R3_HI:
        return R3_HI
    return float(v)
