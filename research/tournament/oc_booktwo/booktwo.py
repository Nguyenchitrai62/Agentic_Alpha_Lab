"""oc_booktwo: two-rung book entry ladder (IDEAS6 #7) pure helpers.

Frozen definitions in PLAN.md. No I/O, no fits, no test-year statistics.
All prices from the minute-0 open O0 once; fills strict trade-through in
[WIN_START, WIN_END); SL/TP multiples unchanged (m_sl=4, m_tp=8 sigma_d).

Usage: pure functions unit-tested in tests/test_oc_booktwo.py and imported
by run_engine.py's patched trade-mode entry (same arithmetic).
"""
from __future__ import annotations

import numpy as np

OFF1 = 0.001   # 10 bps better
OFF2 = 0.0025  # 25 bps better
WIN_START = 5  # minute-5 ban (pipeline run time)
WIN_END = 65   # 60-min expiry: minutes [5,65)
MAKER = 0.0002
TAKER = 0.00055
M_SL = 4.0
M_TP = 8.0  # 2 * m_sl (m_tp None convention)


def split_weights(w: float, variant: str) -> tuple[float, float]:
    """Split total weight w into (w1 @10bps, w2 @25bps)."""
    if variant == "V1":
        return 0.5 * w, 0.5 * w
    if variant == "V2":
        return 0.7 * w, 0.3 * w
    raise ValueError(variant)


def rung_prices(o0: float, sgn: int, variant: str) -> tuple[float, float]:
    """(px1 @10bps, px2 @25bps) better than O0 for side sgn. Variant unused
    for prices (only weights differ); kept for call clarity."""
    _ = variant
    if sgn > 0:
        return o0 * (1 - OFF1), o0 * (1 - OFF2)
    return o0 * (1 + OFF1), o0 * (1 + OFF2)


def first_touch(lows: np.ndarray, highs: np.ndarray, px: float, side: int,
                lo: int = WIN_START, hi: int = WIN_END) -> int | None:
    """First minute m in [lo,hi) with strict trade-through; NaN-safe.

    Buy (side>0): low[m] < px. Sell: high[m] > px. Touch (==) never fills.
    """
    n = min(hi, len(lows), len(highs))
    for m in range(lo, n):
        lo_m, hi_m = lows[m], highs[m]
        if side > 0:
            if np.isfinite(lo_m) and lo_m < px:
                return m
        else:
            if np.isfinite(hi_m) and hi_m > px:
                return m
    return None


def avg_entry(w1: float, px1: float, i1: bool, w2: float, px2: float, i2: bool) -> float:
    """Quantity-weighted average entry of the filled halves (NaN if none)."""
    q = (w1 / px1 if i1 else 0.0) + (w2 / px2 if i2 else 0.0)
    wsum = (w1 if i1 else 0.0) + (w2 if i2 else 0.0)
    if q == 0 or wsum == 0:
        return float("nan")
    return float(wsum / q)


def sl_tp(entry: float, side: int, sd: float,
          m_sl: float = M_SL, m_tp: float = M_TP) -> tuple[float, float]:
    """SL/TP from average entry with the same sd and multiples as G2."""
    return entry * (1 - side * m_sl * sd), entry * (1 + side * m_tp * sd)


def simulate_ladder_window(o0: float, sgn: int, w: float, sd: float,
                           lows: np.ndarray, highs: np.ndarray,
                           opens: np.ndarray, variant: str,
                           m_sl: float = M_SL, m_tp: float = M_TP) -> dict:
    """Sequential minute simulation of one ladder entry over [5,65)+[65,240).

    Fills for resting rungs only in [WIN_START,WIN_END); SL/TP (stop-first)
    checked from the first fill onward every minute to bar end (240). On a
    second fill the average entry + SL/TP are recomputed (be/part stay False
    inside the window; disclosed PLAN simplification). Returns dict with
    fill minutes, average entry, exit (None or (minute, kind, price)), and
    per-minute quantity path (for hand checks). Uses only data at minute m
    for decisions at m (causal). No fees/funding here (engine applies them).
    """
    w1, w2 = split_weights(w, variant)
    px1, px2 = rung_prices(o0, sgn, variant)
    n = min(240, len(lows), len(highs), len(opens))
    f1 = first_touch(lows, highs, px1, sgn)
    f2 = first_touch(lows, highs, px2, sgn)
    # Sequential: walk minutes, fill resting rungs, check SL/TP stop-first.
    filled1 = filled2 = False
    entry = float("nan")
    sl = tp = float("nan")
    exit_ev = None
    qty_path = np.zeros(n)
    cur_q = 0.0
    for m in range(WIN_START, n):
        # fills (only inside the window)
        if m < WIN_END:
            if not filled1 and f1 is not None and m == f1 and exit_ev is None:
                filled1 = True
            if not filled2 and f2 is not None and m == f2 and exit_ev is None:
                filled2 = True
            if (filled1 or filled2) and exit_ev is None and not np.isfinite(entry):
                entry = avg_entry(w1, px1, filled1, w2, px2, filled2)
                # recompute on every new fill inside the window
                sl, tp = sl_tp(entry, sgn, sd, m_sl, m_tp)
            elif exit_ev is None and (filled1 or filled2):
                # second fill updates the average inside the window
                new_e = avg_entry(w1, px1, filled1, w2, px2, filled2)
                if np.isfinite(new_e) and new_e != entry:
                    entry = new_e
                    sl, tp = sl_tp(entry, sgn, sd, m_sl, m_tp)
        if exit_ev is None and (filled1 or filled2):
            # quantity from filled halves
            q = sgn * ((w1 / px1 if filled1 else 0.0) + (w2 / px2 if filled2 else 0.0))
            cur_q = q
            lo_m, hi_m, op_m = lows[m], highs[m], opens[m]
            hit_stop = (np.isfinite(lo_m) and lo_m <= sl) if sgn > 0 else (
                np.isfinite(hi_m) and hi_m >= sl)
            hit_tp = False
            if np.isfinite(hi_m) and np.isfinite(lo_m):
                hit_tp = (hi_m > tp) if sgn > 0 else (lo_m < tp)
            if hit_stop:
                px = min(sl, op_m) if sgn > 0 else max(sl, op_m)
                exit_ev = (m, "stop", float(px))
                cur_q = 0.0
            elif hit_tp:
                exit_ev = (m, "tp", float(tp))
                cur_q = 0.0
        qty_path[m] = cur_q
    return dict(f1=f1, f2=f2, filled1=filled1, filled2=filled2,
                entry=entry, sl=sl, tp=tp, exit=exit_ev, qty_path=qty_path)
