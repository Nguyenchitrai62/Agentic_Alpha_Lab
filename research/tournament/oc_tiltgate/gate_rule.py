"""Pure gate-rule helpers for oc_tiltgate (no data access; unit-tested).

Gate (pre-registered, parameter-free): for anchor A, tilt ON for the whole
year [A, A+365d) iff effect(A) > 0 (strict), where

    effect(A) = sum_{fills i: T_i in [A-372d, A-7d)} (mult_i - 1)*w_i*y10_i
                / n(A),

mult from the fit that was live in the prior year (anchor A-1yr entry of
oc_voltilt fits.json; missing/NaN risk -> 1). assign_mult / anchor_of
semantics are identical to oc_voltilt/tilt_rule.py (imported read-only by
compute_gate.py / run_engine.py; re-implemented here purely so the gate
math is unit-testable without data).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
GATE_LOOKBACK_D = 372
GATE_EMBARGO_D = 7


def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float, lo: float) -> float:
    """Final multiplier for one (coin, holding bar); NaN risk -> 1.0."""
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:  # high risk favourable
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:  # high risk unfavourable
        return lo
    if r <= q20:
        return hi
    return 1.0


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention
    as oc_voltilt/tilt_rule.py)."""
    sh = pd.Timedelta(hours=shift)
    live1 = pd.Timestamp(y1, tz="UTC") + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC") + sh:
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return 4


def gate_window(anchor: str) -> tuple:
    """Exact 12-month gate window [A - 372d, A - 7d) for an anchor date."""
    A = pd.Timestamp(anchor, tz="UTC")
    return (A - pd.Timedelta(days=GATE_LOOKBACK_D),
            A - pd.Timedelta(days=GATE_EMBARGO_D))


def gate_effect(mult, w, y10) -> dict:
    """Pooled per-fill tilt effect: sum((mult-1)*w*y10)/n.

    All inputs aligned arrays over fills in the window. Missing mult is
    passed as NaN and treated as 1 (contributes 0, counts in n).
    Returns dict(effect, n, n_sized) with n_sized = #{mult != 1}.
    """
    mult = np.asarray(mult, dtype=float)
    w = np.asarray(w, dtype=float)
    y10 = np.asarray(y10, dtype=float)
    assert mult.shape == w.shape == y10.shape
    n = int(mult.size)
    if n == 0:
        return dict(effect=float("nan"), n=0, n_sized=0)
    m = np.where(np.isfinite(mult), mult, 1.0)
    eff = float(np.sum((m - 1.0) * w * y10)) / n
    return dict(effect=eff, n=n, n_sized=int(np.sum(m != 1.0)))


def decide(effect: float) -> bool:
    """Gate decision: ON iff effect > 0 (strict; NaN -> OFF)."""
    e = float(effect)
    return bool(np.isfinite(e) and e > 0.0)
