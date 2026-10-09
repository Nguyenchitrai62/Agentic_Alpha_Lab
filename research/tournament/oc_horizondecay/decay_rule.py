"""oc_horizondecay pure decay rule (no data access; unit-tested).

IDEAS8 §4: blend member horizon outputs with frozen decay
  V1: w_h = 1/h, V2: w_h = 1/sqrt(h), renormalised; H = {1,2,6,18}
(H = oc_bookichorizon horizons {1,2,6,18,42} truncated per "beyond 18 excluded").
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

H = (1, 2, 6, 18)

# Frozen renormalised weights (PLAN.md; asserted to sum to 1.0 in code).
_W1_RAW = {h: 1.0 / h for h in H}
_S1 = sum(_W1_RAW.values())  # 31/18
W_HD1 = {h: _W1_RAW[h] / _S1 for h in H}

_W2_RAW = {h: 1.0 / math.sqrt(h) for h in H}
_S2 = sum(_W2_RAW.values())
W_HD2 = {h: _W2_RAW[h] / _S2 for h in H}


def decay_weights(variant: str) -> dict:
    """Frozen renormalised decay weights for HD1 (1/h) or HD2 (1/sqrt(h))."""
    if variant == "HD1":
        return dict(W_HD1)
    if variant == "HD2":
        return dict(W_HD2)
    raise ValueError("variant must be HD1 or HD2")


def blend_members(per_h: dict, variant: str) -> pd.DataFrame:
    """Blend horizon-specific member DataFrames with frozen decay weights.

    per_h: {h: DataFrame} for h in H (identical index/columns).
    Returns sum_h w_h * per_h[h] (renormalised weights sum to 1.0).
    """
    w = decay_weights(variant)
    assert set(per_h) == set(H), f"need horizons {H}, got {sorted(per_h)}"
    assert abs(sum(w.values()) - 1.0) < 1e-12, sum(w.values())
    frames = list(per_h.values())
    idx, cols = frames[0].index, list(frames[0].columns)
    for f in frames[1:]:
        assert f.index.equals(idx) and list(f.columns) == cols
    out = sum(w[h] * per_h[h].astype(float) for h in H)
    return pd.DataFrame(out, index=idx, columns=cols)


def anchor_of(ts: pd.Timestamp, anchors: list) -> int:
    """Year index y such that anchors[y] <= ts < anchors[y]+365d (last year open-ended)."""
    for y in range(len(anchors) - 1, -1, -1):
        if ts >= anchors[y]:
            return y
    raise ValueError(f"timestamp {ts} before first anchor {anchors[0]}")


def exposure_scale(ref: pd.DataFrame, var: pd.DataFrame,
                   idx: pd.DatetimeIndex, anchors: list) -> dict:
    """Per-year mean|var|/mean|ref| on the standard grid (pre-bear; NaN->0)."""
    r = ref.reindex(idx).fillna(0.0).to_numpy(dtype=float)
    v = var.reindex(idx).fillna(0.0).to_numpy(dtype=float)
    out = {}
    for y, a0 in enumerate(anchors):
        m = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
        mr = float(np.abs(r[m]).mean()) if int(m.sum()) else float("nan")
        mv = float(np.abs(v[m]).mean()) if int(m.sum()) else float("nan")
        out[str(a0.date())] = float(mv / mr) if mr > 0 and np.isfinite(mr) else float("nan")
    return out


def apply_exposure_control(ref_std: pd.DataFrame, scale_per_year: dict,
                           anchors: list) -> pd.DataFrame:
    """CC book = REF_book * that year's scalar (after bear, before ffill in engine)."""
    out = ref_std.copy().astype(float)
    idx = ref_std.index
    for y, a0 in enumerate(anchors):
        m = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
        out.loc[m] = out.loc[m] * float(scale_per_year[str(a0.date())])
    return out
