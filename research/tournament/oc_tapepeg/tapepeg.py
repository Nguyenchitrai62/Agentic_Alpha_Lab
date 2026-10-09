"""oc_tapepeg core: D0 base replica + tape-anchored rung placement (pure numpy, no I/O).

Frozen definitions in PLAN.md (IDEAS6 #4). Copies oc_dipexit/exits.py outcome_mu
verbatim (same constants, same stop-first priority); the tape peg is new.

Costs: maker 0.0002 (fill + TP legs), taker 0.00055 (stop/backstop/time legs).
Funding: longs pay 0.0001 iff the timeout exit settles ((T+4h).hour in (0,8,16)).

Tape peg (frozen at the signal close T, causal):
  LOW60 = min 1m low over minutes [T-60m, T-1m] (NaN ignored; all-NaN -> NaN).
  tick  = LOW60 * 0.0001 (1bp proxy for 1 real tick, PLAN tick note).
  peg1  = LOW60 - tick (= LOW60 * 0.9999).
  grid  = 5 * tick; peg2 = floor(peg1 / grid) * grid (= 0.9995 * LOW60).
  rung(V1) = min(sigma_price, peg1); rung(V2) = min(sigma_price, peg2).
  Non-finite / non-positive LOW60 or peg -> sigma price (no peg that bar).
  Frozen at T: never updated inside the live window.
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
# Frozen tick proxies (PLAN.md tick note): 1tick = 1bp of LOW60, 5-tick grid = 5bp.
TICK_BP = 0.0001
GRID_MULT = 5
LOOKBACK = 60


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


def trailing_low(low_before: np.ndarray):
    """LOW60 = min low over the 60 fully closed minutes strictly before T.

    low_before: length-60 array of 1m lows for minutes [T-60m, T-1m].
    NaN ignored; all-NaN -> NaN. Never touches the placement window.
    """
    a = np.asarray(low_before, dtype=float)
    if a.size == 0:
        return np.nan
    if np.isfinite(a).any():
        return float(np.nanmin(a))
    return np.nan


def tape_peg(low60: float):
    """Return (peg1, peg2) for a finite positive LOW60, else (nan, nan).

    peg1 = LOW60 - 1tick; peg2 = floor(peg1 / 5tick) * 5tick.
    """
    if not np.isfinite(low60) or low60 <= 0:
        return (np.nan, np.nan)
    tick = low60 * TICK_BP
    if not np.isfinite(tick) or tick <= 0:
        return (np.nan, np.nan)
    peg1 = low60 - tick
    grid = GRID_MULT * tick
    peg2 = np.floor(peg1 / grid) * grid
    return (float(peg1), float(peg2))


def rung_px(o1: float, sg: float, k: float, low60: float):
    """Triple (base, V1, V2) rung prices frozen at T.

    Falls back to the sigma price wherever the peg is unusable.
    """
    lv = float(o1) * (1 - float(k) * float(sg))
    peg1, peg2 = tape_peg(low60)
    v1 = min(lv, peg1) if np.isfinite(peg1) and peg1 > 0 else lv
    v2 = min(lv, peg2) if np.isfinite(peg2) and peg2 > 0 else lv
    return (float(lv), float(v1), float(v2))


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
