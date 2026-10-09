"""oc_d_stagger: pure helpers (no data access; unit-tested).

Frozen rule (see PLAN.md, IDEAS12 #5):
- split each rung 50/50 at the same frozen sigma price lv.
- V1: half A live offsets 5..64, half B live 35..94 (60 bars each).
- V2: half A live 5..64, half B live 95..154.
- REF (base replica): live 16..238.
- strict low < lv trade-through; NaN never fills; minute-5 ban (nothing < 5).
- w_h = 0.5/(1+n(f_h)) B1 at own fill minute; outcomes VERBATIM outcome_mu mu=1.0.
"""
from __future__ import annotations

import numpy as np

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5

# frozen windows: (start_offset, end_offset) inclusive, offsets after bar open T
WIN_A = (5, 64)
WIN_B_V1 = (35, 94)
WIN_B_V2 = (95, 154)
WIN_REF = (16, 238)

PHASES = (0, 1, 2, 3)


def windows_V1():
    return (WIN_A, WIN_B_V1)


def windows_V2():
    return (WIN_A, WIN_B_V2)


def find_fill_in(low_arr: np.ndarray, level: float, start: int, end: int):
    """First offset f in [start, end] (absolute bar offsets 0..239) with low < level.

    low_arr: 240-min low array for the bar. STRICT trade-through. NaN never fills.
    Returns int offset or None.
    """
    lv = float(level)
    if not np.isfinite(lv):
        return None
    lo = max(int(start), 0)
    hi = min(int(end), 239)
    if hi < lo:
        return None
    win = np.asarray(low_arr, dtype=float)[lo:hi + 1]
    hit = np.isfinite(win) & (win < lv)
    if hit.any():
        return lo + int(np.argmax(hit))
    return None


def n_at(close_others: np.ndarray, open_others: np.ndarray,
         sigma_others: np.ndarray) -> int:
    """B1 correlation count at a single fill minute (v399-exact, scalar version).

    close_others: 1m closes of OTHER coins at minute T+f-1 (NaN = not flushing).
    open_others/sigma_others: O/sg at decision bar T for other coins.
    """
    n = 0
    co = np.asarray(close_others, dtype=float)
    oo = np.asarray(open_others, dtype=float)
    ss = np.asarray(sigma_others, dtype=float)
    for c, o, sg in zip(co, oo, ss):
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        if np.isfinite(c) and c <= thr:
            n += 1
    return int(n)


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """v399-exact correlation count per live minute (matrix version, replica core)."""
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


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """VERBATIM replica outcome branch (oc_placebo_dip/build_ledger_presample).

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


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
                 o2: float, settle: bool) -> str:
    """Kind only ('tp'/'time'/'stop'/'backstop'), same branch as outcome_mu."""
    _, _, how = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, mu, o2, settle)
    return how


def compute_sigma(opens: np.ndarray) -> np.ndarray:
    """VERBATIM presample compute_sigma: pct_change rolling-360 min_periods-120 shift-1."""
    import pandas as pd
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def phase_mean_sums(ph, yr, wv, yv, n_years: int):
    """Per-year 4-phase-mean sums (same as k2placebo phase_mean_sums)."""
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


KIND_CODE = {"unfilled": -1, "unknown": -2, "tp": 0, "time": 1, "stop": 2, "backstop": 3}
KIND_NAME = {v: k for k, v in KIND_CODE.items()}


def half_weight(n_fill: int) -> float:
    """Frozen half weight: 0.5 * B1 at own fill minute."""
    return 0.5 / (1 + int(n_fill))
