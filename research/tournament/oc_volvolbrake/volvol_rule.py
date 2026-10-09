"""oc_volvolbrake pure rule helpers (no data access; unit-tested).

Causal contract: RV6(T) uses only 4h closes <= T; D(d) is RV6 at d 00:00;
f(T) uses 30 daily D on days strictly before T's day; thresholds are frozen
per-anchor quantiles; gates are strict comparisons; NaN never gates.
"""
from __future__ import annotations

import numpy as np

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
MIN_NORM = 1000


def rv6_from_returns(R: np.ndarray) -> float:
    """Std(ddof=1) of 6 log returns ending <= T; NaN unless 6 finite."""
    R = np.asarray(R, dtype=float)
    assert R.shape == (6,)
    if not np.all(np.isfinite(R)):
        return float("nan")
    return float(np.std(R, ddof=1))


def fragility_from_daily(D: np.ndarray) -> float:
    """Std(ddof=1) of 30 daily RV6 values; NaN unless 30 finite."""
    D = np.asarray(D, dtype=float)
    assert D.shape == (30,)
    if not np.all(np.isfinite(D)):
        return float("nan")
    return float(np.std(D, ddof=1))


def gate_level(f: float, q: float) -> bool:
    """Vol-of-vol brake gate: strictly greater; NaN never gates."""
    if not np.isfinite(f) or not np.isfinite(q):
        return False
    return bool(f > q)


def anchor_of(T_ns: np.ndarray, anch_ns: np.ndarray) -> np.ndarray:
    """Index of the anchor year each timestamp belongs to (right-closed)."""
    T_ns = np.asarray(T_ns, dtype=np.int64)
    anch_ns = np.asarray(anch_ns, dtype=np.int64)
    return np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)


def control_mult(gate_share: float) -> float:
    """Exposure-matched constant multiplier: 1 - 0.5*share."""
    s = float(gate_share)
    assert 0.0 <= s <= 1.0
    return 1.0 - 0.5 * s
