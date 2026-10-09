"""Pure thin-book calendar helpers for oc_d_calendar (no data access; unit-tested).

Frozen rule (see PLAN.md, IDEAS12 section 4):
  V1(T) = 1.25 iff T is Saturday/Sunday UTC else 1.0.
  V2(T) = 1.20 iff 0 <= hour(T) < 8 UTC else 1.0.
  "Signal bar" = the dip decision holding-bar open T (UTC). Timestamps only;
  no price is read for the trigger. Missing/NaT -> 1.0 (inert).

Stop-kind helpers are VERBATIM build_ledger_presample.outcome_mu logic at mu=1.0
(sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+mu*sg); close5 4sg stop + 8sg
backstop + TP + timeout at next 4h open; stop-first ordering backstop > tp > stop).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HI_V1 = 1.25  # frozen weekend mult
HI_V2 = 1.20  # frozen session mult
MID = 1.0

RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0


def _as_utc(t) -> pd.Timestamp | None:
    try:
        q = pd.Timestamp(t)
    except Exception:
        return None
    if q is pd.NaT or pd.isna(q):
        return None
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    else:
        q = q.tz_convert("UTC")
    return q


def mult_V1(t) -> float:
    """Weekend tilt: 1.25 on Sat/Sun UTC else 1.0. Pure."""
    q = _as_utc(t)
    if q is None:
        return float(MID)
    return float(HI_V1) if q.weekday() in (5, 6) else float(MID)


def mult_V2(t) -> float:
    """Session tilt: 1.2 on 00-08 UTC else 1.0. Pure."""
    q = _as_utc(t)
    if q is None:
        return float(MID)
    return float(HI_V2) if 0 <= q.hour < 8 else float(MID)


def mult_at(t, variant: str) -> float:
    """Dispatch helper. Pure."""
    if variant == "V1":
        return mult_V1(t)
    if variant == "V2":
        return mult_V2(t)
    raise ValueError(f"unknown variant {variant!r}")


def phase_mean_sums(ph, yr, wv, yv, n_years: int = 4):
    """Per-year 4-phase-mean sums (same as k2placebo scoring). Pure."""
    out = []
    for y in range(int(n_years)):
        ss = []
        for p in (0, 1, 2, 3):
            m = (np.asarray(ph) == p) & (np.asarray(yr) == y)
            ss.append(float((np.asarray(wv)[m] * np.asarray(yv)[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
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
