"""Pure risk-parity helpers for oc_d_riskparity (no data access; unit-tested).

Frozen rule (see PLAN.md, IDEAS12 section 3):
  parity equalises the OPEN-to-stop dollar risk per rung:
    stopDist_k = (k + stop_sg_k) * sg(T)  (rung depth + entry->stop, in sg units)
    m_k = 4 / (k + stop_sg_k)             (numerator 4 = frozen base stop in sg)
  V1: base 5-rung grid k in {2.5,3,3.5,4,5}, uniform frozen 4sg stops.
  V2: 4-rung grid k' in {2.5,3.5,4.5,5.5} with depth-scaled stops {4,5,6,7}.
  Backstop frozen 8sg; TP legs 0.9/1.0/1.1; B1 w = 1/(1+n); live 16..238 strict.
  Outcome branches VERBATIM build_ledger_presample.outcome_mu /
  compute_placebo_dip.outcome_mu (mu legs; stop-first ordering backstop > tp > stop).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RUNGS_V1 = (2.5, 3.0, 3.5, 4.0, 5.0)
STOPS_V1 = (4.0, 4.0, 4.0, 4.0, 4.0)
RUNGS_V2 = (2.5, 3.5, 4.5, 5.5)
STOPS_V2 = (4.0, 5.0, 6.0, 7.0)
BACKSTOP = 8.0
NUMER = 4.0  # frozen base stop in sg units (IDEAS12 "4sg/stopDist")

LIVE_A, LIVE_B = 16, 238
DETECT_K = 2.5


def parity_mults_V1() -> dict:
    """Frozen V1 parity mult per base rung index 0..4: 4/(k+4). Pure."""
    return {i: float(NUMER / (k + s)) for i, (k, s) in
            enumerate(zip(RUNGS_V1, STOPS_V1))}


def parity_mults_V2() -> dict:
    """Frozen V2 parity mult per V2 rung index 0..3: 4/(k'+s'). Pure."""
    return {i: float(NUMER / (k + s)) for i, (k, s) in
            enumerate(zip(RUNGS_V2, STOPS_V2))}


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


def _outcome_branch(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
                    o2: float, settle: bool, m_sl: float,
                    maker: float = 0.0002, taker: float = 0.00055,
                    fund: float = 0.0001):
    """Shared VERBATIM outcome branch with a per-call stop multiple. Pure."""
    sl = lv * (1 - m_sl * sg)
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
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - maker - taker, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * maker, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = float(Oa[km + 1]), km + 1
        else:
            px, x = float(o2), 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - maker - taker
        if x == 240 and settle:
            ret -= fund
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time")
    return (float(o2) / lv - 1 - maker - taker - (fund if settle else 0.0), x, "time")


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """Base outcome (frozen 4sg stop) VERBATIM the replica builders. Pure."""
    return _outcome_branch(Ha, La, Ca, Oa, f, lv, sg, mu, o2, settle, m_sl=4.0)


def outcome_mu_v2(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
                  o2: float, settle: bool, m_sl: float):
    """V2 outcome with a per-rung stop multiple (backstop still 8sg). Pure."""
    return _outcome_branch(Ha, La, Ca, Oa, f, lv, sg, mu, o2, settle,
                           m_sl=float(m_sl))


def outcome_kind(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                 mu: float = 1.0) -> str:
    """Exit-kind branch (base 4sg stop). Pure."""
    _, _, kind = _outcome_branch(Ha, La, Ca, Oa, f, lv, sg, mu, np.nan, False,
                                 m_sl=4.0)
    return kind


def outcome_kind_v2(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                    m_sl: float, mu: float = 1.0) -> str:
    """Exit-kind branch with a per-rung stop multiple. Pure."""
    _, _, kind = _outcome_branch(Ha, La, Ca, Oa, f, lv, sg, mu, np.nan, False,
                                 m_sl=float(m_sl))
    return kind


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
