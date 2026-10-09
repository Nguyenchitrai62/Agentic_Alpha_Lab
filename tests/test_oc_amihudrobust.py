"""oc_amihudrobust tests: causality/truncation + hand-checked synthetic case."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1] if (HERE.parents[1] / "research").exists() else Path(".")
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_amihudrobust"))
from amihud_signal import (  # noqa: E402
    SYMS,
    a1_mult,
    clip_mult,
    d_last,
    load_daily,
    raw_amihud_matrix,
    xs_z,
)


def test_signal_truncation_causal():
    """Recompute Amihud30 at D0 from data truncated to <=D0 (matches 1e-12);
    +-1s boundary exposes exactly the prior day; sampled-T truncation leaves
    multipliers unchanged."""
    sym = "BTCUSDT"
    d = load_daily(sym)
    # pick a day well inside history with full window
    D0 = pd.Timestamp("2022-03-15", tz="UTC")
    assert D0 in d.index
    # full-history rolling value at D0
    full = d["amihud_d"].rolling(30, min_periods=20).mean().loc[D0]
    # truncated recompute
    trunc = d.loc[:D0]
    part = trunc["amihud_d"].rolling(30, min_periods=20).mean().iloc[-1]
    assert np.isfinite(full) and np.isfinite(part)
    assert abs(float(full) - float(part)) < 1e-12
    # boundary: T = D0+1 00:00 +- 1s
    T_at = pd.DatetimeIndex([D0 + pd.Timedelta(days=1)])
    T_before = pd.DatetimeIndex([D0 + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)])
    assert d_last(pd.to_datetime(T_at, utc=True))[0] == D0
    assert d_last(pd.to_datetime(T_before, utc=True))[0] == D0 - pd.Timedelta(days=1)
    # sampled-T truncation: multipliers from truncated daily history == full
    T = pd.date_range("2022-03-10", "2022-03-20", freq="4h", tz="UTC")
    f_full, _ = a1_mult(T, cols=SYMS)
    # truncate each daily cache to <= max usable day and recompute
    Dmax = d_last(T).max()
    saved = {}
    import amihud_signal as sig

    for s in SYMS:
        dd = sig.load_daily(s)
        saved[s] = dd
        sig._daily_cache[s] = dd.loc[:Dmax].copy()
    sig._raw_cache.clear()
    try:
        f_tr, _ = a1_mult(T, cols=SYMS)
    finally:
        for s in SYMS:
            sig._daily_cache[s] = saved[s]
        sig._raw_cache.clear()
    pd.testing.assert_frame_equal(f_full, f_tr)


def test_handchecked_synthetic():
    """Hand-checked z/clip/K maths on a tiny matrix."""
    mat = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
    z = xs_z(mat)
    mu = 3.0
    sd = float(np.std([1, 2, 3, 4, 5], ddof=1))  # sqrt(2.5)
    exp = (np.array([1, 2, 3, 4, 5], float) - mu) / sd
    assert np.allclose(z[0], exp, atol=1e-12)
    m = clip_mult(1.0 + 0.25 * z)
    assert np.allclose(m[0], np.clip(1 + 0.25 * exp, 0.5, 1.5), atol=1e-12)
    # degenerate: std 0 -> zeros; NaN raw -> NaN z -> mult 1
    z0 = xs_z(np.array([[2.0, 2.0, 2.0, 2.0, 2.0]]))
    assert (z0[0] == 0.0).all()
    zn = xs_z(np.array([[np.nan, 1.0, 2.0, 3.0, 4.0]]))
    assert np.isnan(zn[0, 0]) and np.isfinite(zn[0, 1:]).all()
    mn = clip_mult(np.array([[np.nan, 2.0]]))
    assert mn[0, 0] == 1.0 and mn[0, 1] == 1.5  # 2.0 clipped to 1.5
    # d_last mapping
    T = pd.DatetimeIndex(["2022-01-02 04:00"])
    assert d_last(pd.to_datetime(T, utc=True))[0] == pd.Timestamp("2022-01-01", tz="UTC")
    # raw matrix shape
    T2 = pd.date_range("2022-04-01", "2022-04-02", freq="4h", tz="UTC")
    M = raw_amihud_matrix(T2, 30, 20, SYMS)
    assert M.shape == (len(T2), 5)
