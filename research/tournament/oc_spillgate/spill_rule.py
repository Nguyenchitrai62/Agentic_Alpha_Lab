"""oc_spillgate pure rule helpers (no data access; unit-tested).

Causal contract: c(T)/d(T) use only 4h closes <= T; thresholds are frozen
per-anchor quantiles; gates are strict comparisons; NaN never gates.
"""
from __future__ import annotations

import numpy as np

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
N_PAIRS_REQUIRED = 8
MIN_OVERLAP = 5


def pairwise_mean_corr(R: np.ndarray) -> float:
    """Mean pairwise Pearson over columns of R (n_obs x 5).

    R rows are trailing 4h returns ending <= T. Pairwise-complete; a pair is
    NaN if < MIN_OVERLAP overlapping finite obs or either leg has zero
    variance. Returns NaN if < N_PAIRS_REQUIRED of 10 pairs valid.
    """
    R = np.asarray(R, dtype=float)
    assert R.ndim == 2 and R.shape[1] == 5
    corrs = []
    for i in range(5):
        for j in range(i + 1, 5):
            x = R[:, i]
            y = R[:, j]
            m = np.isfinite(x) & np.isfinite(y)
            if int(m.sum()) < MIN_OVERLAP:
                corrs.append(np.nan)
                continue
            xa = x[m] - x[m].mean()
            yb = y[m] - y[m].mean()
            den = float(np.sqrt(float(xa @ xa) * float(yb @ yb)))
            if not np.isfinite(den) or den <= 0:
                corrs.append(np.nan)
                continue
            corrs.append(float((xa @ yb) / den))
    corrs = np.array(corrs, dtype=float)
    ok = np.isfinite(corrs)
    if int(ok.sum()) < N_PAIRS_REQUIRED:
        return float("nan")
    return float(corrs[ok].mean())


def gate_level(c: float, q90: float) -> bool:
    """S1 level gate: strictly greater; NaN never gates."""
    if not np.isfinite(c) or not np.isfinite(q90):
        return False
    return bool(c > q90)


def gate_change(d: float, q95: float) -> bool:
    """S2 change-spike gate: strictly greater; NaN never gates."""
    if not np.isfinite(d) or not np.isfinite(q95):
        return False
    return bool(d > q95)


def anchor_of(T_ns: np.ndarray, anch_ns: np.ndarray) -> np.ndarray:
    """Index of the anchor year each timestamp belongs to (right-closed).

    y = clip(searchsorted(anch, T, side='right') - 1, 0, 4).
    T before the first anchor maps to year 0 (caller forces pre-2021 rows
    ungated anyway).
    """
    T_ns = np.asarray(T_ns, dtype=np.int64)
    anch_ns = np.asarray(anch_ns, dtype=np.int64)
    return np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)


def control_mult(gate_share: float) -> float:
    """Exposure-matched constant multiplier: 1 - 0.5*share."""
    s = float(gate_share)
    assert 0.0 <= s <= 1.0
    return 1.0 - 0.5 * s
