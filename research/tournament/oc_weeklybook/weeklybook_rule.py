"""oc_weeklybook: weekly-decision book sleeve (IDEAS10 #6) pure helpers.

Frozen definitions in PLAN.md. No I/O, no fits, no test-year statistics.
w_fast = post-bear 4h book row at T; w_slow = post-bear book at last weekly
anchor W* <= T (Wednesday 00 UTC frozen; other weekdays diagnostic only);
w_V = w_fast + f * w_slow with f 0.10 (V1) / 0.25 (V2) frozen ex-ante.
"""
from __future__ import annotations

import numpy as np

F_V1 = 0.10
F_V2 = 0.25
WEDNESDAY = 2  # Monday=0 .. Sunday=6; Wednesday frozen ex-ante
COST_PROXY = 0.0005


def weekly_anchors(index, weekday: int = WEDNESDAY) -> np.ndarray:
    """Boolean mask: True at weekly anchor rows (that weekday, 00:00 UTC).

    index: DatetimeIndex (tz-aware UTC). Strictly a function of the timestamp:
    midnight + matching weekday. No data used, so causal by construction.
    """
    if weekday not in range(7):
        raise ValueError(f"weekday must be 0..6, got {weekday}")
    hod = index.hour + index.minute / 60.0 + index.second / 3600.0
    return ((np.asarray(hod) == 0.0) & (np.asarray(index.weekday) == weekday))


def sample_slow(postbear: np.ndarray, anchor_mask: np.ndarray) -> np.ndarray:
    """Weekly-held slow leg: at each row, last anchor row's value (0 before first).

    postbear: (n, k) post-bear book weights (NaN->0 inside). anchor_mask: (n,)
    bool. Causal: row i uses only rows j <= i with anchor_mask[j].
    """
    w = np.nan_to_num(np.asarray(postbear, dtype=float), nan=0.0)
    m = np.asarray(anchor_mask, dtype=bool)
    if w.shape[0] != m.shape[0]:
        raise ValueError(f"shape mismatch {w.shape} vs {m.shape}")
    n = w.shape[0]
    out = np.zeros_like(w)
    cur = np.zeros(w.shape[1])
    started = False
    for i in range(n):
        if m[i]:
            cur = w[i].copy()
            started = True
        out[i] = cur if started else 0.0
    return out


def overlay(fast: np.ndarray, slow: np.ndarray, f: float) -> np.ndarray:
    """Additive sleeve: fast + f * slow (NaN->0 inside)."""
    if f not in (F_V1, F_V2):
        raise ValueError(f"frozen f only 0.10/0.25, got {f}")
    a = np.nan_to_num(np.asarray(fast, dtype=float), nan=0.0)
    b = np.nan_to_num(np.asarray(slow, dtype=float), nan=0.0)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    return a + float(f) * b


def control_mult_per_year(ref_abs_sum: float, var_abs_sum: float) -> float:
    """Exposure-matched constant for one year: sum|var| / sum|ref| (1.0 if ref 0)."""
    try:
        r = float(ref_abs_sum)
        v = float(var_abs_sum)
    except (TypeError, ValueError):
        return 1.0
    if not (np.isfinite(r) and np.isfinite(v)) or r <= 0:
        return 1.0
    c = v / r
    if not np.isfinite(c) or c < 0:
        return 1.0
    return float(c)


def proxy_net_returns(weights: np.ndarray, fwd: np.ndarray,
                      cost: float = COST_PROXY) -> np.ndarray:
    """Per-bar portfolio net returns for the LIGHT scoring proxy.

    weights: (n,k) book rows in grid order; fwd: (n,k) open-to-open returns;
    each leg's own prev (first prev 0): net = sum_s (W*R1 - cost*|W-W_prev|).
    """
    w = np.nan_to_num(np.asarray(weights, dtype=float), nan=0.0)
    r = np.nan_to_num(np.asarray(fwd, dtype=float), nan=0.0)
    if w.shape != r.shape:
        raise ValueError(f"shape mismatch {w.shape} vs {r.shape}")
    prev = np.zeros_like(w)
    prev[1:] = w[:-1]
    return (w * r - float(cost) * np.abs(w - prev)).sum(axis=1)


def sleeve_corr(fast_rp: np.ndarray, slow_rp: np.ndarray) -> float:
    """Pearson corr of two per-bar return series (NaN if degenerate)."""
    a = np.asarray(fast_rp, dtype=float)
    b = np.asarray(slow_rp, dtype=float)
    if a.shape != b.shape or len(a) < 3:
        return float("nan")
    m = np.isfinite(a) & np.isfinite(b)
    if int(m.sum()) < 3:
        return float("nan")
    a, b = a[m], b[m]
    if float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
        return float("nan")
    c = float(np.corrcoef(a, b)[0, 1])
    return c if np.isfinite(c) else float("nan")
