"""Pure drawdown-rank helpers for oc_d_ddrank (no data access; unit-tested).

Frozen rule (see PLAN.md, IDEAS12 §1):
  DD-depth[j] at decision bar open T[j] uses only closes with close_time <= T[j]:
  current = C[j-1] (just-closed bar), window = C[j-180..j-1] (180 bars = frozen 30d),
  DD = (max(window) - current) / max(window); NaN if < 60 finite or bad values.
  Per (shift, T): rank finite-DD coins deepest-first (ties: sym alphabetical);
  V1: deepest 1.25 / shallowest 0.75 / middle 1.0 (N==1 -> 1.0; N==2 -> 1.25/0.75);
  V2: top-2 deep 1.25 else 1.0 (N==1 -> 1.0). Missing DD -> 1.0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK = 180  # frozen 30d x 6 bars/day
MIN_PERIODS = 60  # frozen
HI = 1.25  # frozen K2-family mults
MID = 1.0
LO = 0.75

RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0


def dd_depth_series(closes, lookback: int = LOOKBACK,
                    min_periods: int = MIN_PERIODS) -> np.ndarray:
    """DD-depth available at each bar open T[j].

    closes: array-like of 4h closes in grid order (float, NaN allowed).
    Returns float array same length: DD[j] uses C[j-lookback..j-1] only
    (strictly prior bars; the decision bar's own close is NOT used).
    Pure + causal by construction.
    """
    c = np.asarray(closes, dtype=float)
    n = c.size
    out = np.full(n, np.nan)
    if n == 0:
        return out
    for j in range(1, n):
        lo = max(0, j - int(lookback))
        win = c[lo:j]  # C[lo..j-1], excludes bar j itself
        fin = win[np.isfinite(win)]
        if fin.size < int(min_periods):
            continue
        cur = c[j - 1]
        if not np.isfinite(cur):
            continue
        mx = float(np.max(fin))
        if not np.isfinite(mx) or mx <= 0:
            continue
        out[j] = (mx - float(cur)) / mx
    return out


def rank_mults(dd: dict, hi: float = HI, mid: float = MID,
               lo: float = LO) -> dict:
    """Map {sym: DD-depth (NaN = missing)} -> {sym: (mult_V1, mult_V2)}.

    Deterministic, fit-free: sort finite-DD syms by (-DD, sym).
    V1: rank0 -> hi; rank N-1 -> lo; others mid; N<=1 -> all mid.
    V2: ranks 0,1 (if N>=2) -> hi else mid; N==1 -> mid.
    Missing-DD syms -> (mid, mid). Pure.
    """
    finite = {s: float(v) for s, v in dd.items() if np.isfinite(v)}
    order = sorted(finite.keys(), key=lambda s: (-finite[s], str(s)))
    n = len(order)
    out: dict = {}
    for s in dd.keys():
        out[s] = (float(mid), float(mid))
    if n == 0:
        return out
    if n == 1:
        return out  # no cross-section
    # V1
    for i, s in enumerate(order):
        if i == 0:
            out[s] = (float(hi), out[s][1])
        elif i == n - 1:
            out[s] = (float(lo), out[s][1])
    # V2 top-2
    top2 = set(order[:2])
    for s in order:
        v1, _ = out[s]
        out[s] = (v1, float(hi) if s in top2 else float(mid))
    return out


def compute_sigma(opens) -> np.ndarray:
    """Presample level sigma VERBATIM build_ledger_presample.compute_sigma."""
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def find_fill(low_win, level: float):
    """First index with low < level (strict trade-through), else None. Pure."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                 mu: float = 1.0) -> str:
    """Exit-kind branch VERBATIM build_ledger_presample.outcome_mu ordering."""
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        return "backstop"
    if kt is not None and (ks is None or kt < ks):
        return "tp"
    if ks is not None:
        return "stop"
    return "time"
