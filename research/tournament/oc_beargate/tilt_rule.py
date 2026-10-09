"""Pure tilt-rule helpers for oc_beargate (no data access; unit-tested).

Base rule (identical to C2 / V_GARCH): per anchor A, direction = sign of
Spearman(risk, y_dep), edges q20/q80 of risk. Multiplier hi in the favourable
outer quintile, lo in the unfavourable outer quintile, 1 otherwise;
missing/NaN risk -> 1. Both legs: hi/lo = 1.25/0.75.
Gate (no new parameter): C2_B = m_C2 if not bear else 1.0;
GARCH_B = m_G if not bear else 1.0, where bear is the exact v421 bear state
(v421_gross_cap.py:70) evaluated at the holding-bar open from data <= T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


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


def gate_mult(m_base: float, is_bear: bool) -> float:
    """Bear gate: tilt applies only when G2's own filter says not bear."""
    if bool(is_bear):
        return 1.0
    m = float(m_base)
    return m if np.isfinite(m) else 1.0


def anchor_of(t, shift: int, y1: str = "2026-09-23") -> int:
    """Year index 0..4 of holding-bar open T on phase shift (same convention as
    oc_kronosmanual: year y covers [ANCH5[y]+sh, min(+365d, live1)))."""
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


def bear_series_from_btc(btc: pd.Series, window: int = 1200,
                         min_periods: int = 600) -> pd.Series:
    """Exact v421 bear definition (v421_gross_cap.py:70), pure helper for tests.

    bear = (btc < btc.rolling(window, min_periods=min_periods).mean()).
    NaN rolling -> False (pandas comparison semantics preserved here explicitly).
    """
    ma = btc.rolling(window, min_periods=min_periods).mean()
    out = (btc < ma).fillna(False).astype(bool)
    return out


def bear_at(bear_idx_ns: np.ndarray, bear_val: np.ndarray, t_ns: int) -> bool:
    """Latest bear state at standard-grid index <= T (ffill, causal).

    bear_idx_ns: sorted int64 ns of bear_std index; bear_val: bool array.
    Returns False when no index <= T (before history).
    """
    import bisect  # local import: keep module dependency-free otherwise
    pos = bisect.bisect_right(list(bear_idx_ns), int(t_ns)) - 1
    if pos < 0:
        return False
    return bool(bear_val[pos])
