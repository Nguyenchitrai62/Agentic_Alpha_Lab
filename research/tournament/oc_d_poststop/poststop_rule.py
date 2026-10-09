"""Pure post-stop helpers for oc_d_poststop (no data access; unit-tested).

Frozen rule (see PLAN.md, IDEAS12 section 2):
  after a dip stop on coin c (VERBATIM ledger exit branch at mu=1.0, kind in
  {stop, backstop}, exit minute x -> tc = T + x min), size c's new rungs x1.25
  for N days on the SAME (coin, shift). V1 N=7, V2 N=3. Else 1.0.

Exit-branch arithmetic VERBATIM from
oc_presampletilt build_ledger_presample.outcome_mu /
oc_placebo_dip compute_placebo_dip.outcome_mu (mu=1.0 leg; stop-first ordering).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BOOST = 1.25
FLAT = 1.0
V1_DAYS = 7
V2_DAYS = 3
NS_DAY = 86_400_000_000_000

RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0


def compute_sigma(opens) -> np.ndarray:
    """Level sigma VERBATIM build_ledger_presample.compute_sigma.

    pct_change rolling-360 min_periods-120 shift-1 on opens. Pure.
    """
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def find_fill(low_win, level: float):
    """First index with low < level (strict trade-through), else None. Pure."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_kind_x(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                   mu: float = 1.0):
    """VERBATIM outcome_mu exit branch; returns (kind, x).

    kind in {"backstop","tp","stop","time"}; x = exit minute offset
    (240 = next-bar open). Costs omitted (kind/timing only). Pure.
    """
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
        return ("backstop", f + 1 + kb)
    if kt is not None and (ks is None or kt < ks):
        return ("tp", f + 1 + kt)
    if ks is not None:
        km = f + 1 + ks
        x = km + 1 if km + 1 < 240 else 240
        return ("stop", x)
    return ("time", 240)


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                 mu: float = 1.0) -> str:
    """Kind only (wraps outcome_kind_x). Pure."""
    kind, _ = outcome_kind_x(Ha, La, Ca, Oa, f, lv, sg, mu)
    return kind


def boosted_mult(grid_ns: np.ndarray, trig_ns: np.ndarray, n_days: int,
                 boost: float = BOOST, flat: float = FLAT) -> np.ndarray:
    """Per grid time T: boost iff exists tc with 0 < T - tc <= n_days.

    Both arrays int64 ns; trig_ns must be sorted. Pure (searchsorted on the
    latest tc strictly before T) — causal by construction (T == tc never boosts).
    """
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(trig_ns, dtype=np.int64)
    out = np.full(len(grid_ns), float(flat))
    if trig_ns.size == 0:
        return out
    span = int(n_days) * NS_DAY
    pos = np.searchsorted(trig_ns, grid_ns, side="left") - 1
    valid = pos >= 0
    hit = np.zeros(len(grid_ns), dtype=bool)
    hit[valid] = (grid_ns[valid] - trig_ns[pos[valid]] <= span)
    out[hit] = float(boost)
    return out


def phase_mean_sums(ph, yr, wv, yv, n_years: int):
    """Per-year 4-phase-mean sums (same as k2placebo phase_mean_sums). Pure."""
    ph = np.asarray(ph)
    yr = np.asarray(yr)
    wv = np.asarray(wv, dtype=float)
    yv = np.asarray(yv, dtype=float)
    out = []
    for y in range(int(n_years)):
        ss = []
        for p in (0, 1, 2, 3):
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out
