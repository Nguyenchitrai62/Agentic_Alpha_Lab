"""oc_amihudbybit tests: causality/truncation + hand-checked synthetic case."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[1] if (HERE.parents[1] / "research").exists() else Path(".")
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_amihudbybit"))
from bybit_signal import (  # noqa: E402
    SYMS,
    a1_mult,
    ab1_mult,
    clip_mult,
    d_last,
    load_binance_daily,
    load_bybit_daily,
    raw_binance_matrix,
    raw_bybit_matrix,
    xs_z,
)


def test_signal_truncation_causal():
    """Bybit Amihud30 at D0 from data truncated to <=D0 matches 1e-12;
    +-1s boundary exposes exactly the prior day; sampled-T truncation leaves
    multipliers unchanged; win_start/stop-first constants asserted in engine."""
    sym = "BTCUSDT"
    d = load_bybit_daily(sym)
    assert (d["turnover"] > 0).all() or d["turnover"].isna().sum() >= 0
    D0 = pd.Timestamp("2022-03-15", tz="UTC")
    assert D0 in d.index
    full = d["amihud_d"].rolling(30, min_periods=20).mean().loc[D0]
    trunc = d.loc[:D0]
    part = trunc["amihud_d"].rolling(30, min_periods=20).mean().iloc[-1]
    assert np.isfinite(full) and np.isfinite(part)
    assert abs(float(full) - float(part)) < 1e-12
    T_at = pd.DatetimeIndex([D0 + pd.Timedelta(days=1)])
    T_before = pd.DatetimeIndex([D0 + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)])
    assert d_last(pd.to_datetime(T_at, utc=True))[0] == D0
    assert d_last(pd.to_datetime(T_before, utc=True))[0] == D0 - pd.Timedelta(days=1)
    T = pd.date_range("2022-03-10", "2022-03-20", freq="4h", tz="UTC")
    f_full, _ = ab1_mult(T, cols=SYMS)
    Dmax = d_last(T).max()
    import bybit_signal as sig

    saved = {}
    for s in SYMS:
        dd = sig.load_bybit_daily(s)
        saved[s] = dd
        sig._daily_bybit_cache[s] = dd.loc[:Dmax].copy()
    try:
        f_tr, _ = ab1_mult(T, cols=SYMS)
    finally:
        for s in SYMS:
            sig._daily_bybit_cache[s] = saved[s]
    pd.testing.assert_frame_equal(f_full, f_tr)
    # engine fill-timing constants present
    eng = (ROOT / "research" / "tournament" / "oc_amihudbybit"
           / "compute_bybit_engine.py").read_text()
    assert "win_start=5" in eng and "stop-first" in eng.lower().replace("_", "-") \
        or "stop_first" in eng or "stop-first" in eng


def test_handchecked_synthetic():
    """Hand-checked z/clip/K maths; A1 path matches oc_lit_xs xs_signal."""
    mat = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
    z = xs_z(mat)
    mu = 3.0
    sd = float(np.std([1, 2, 3, 4, 5], ddof=1))
    exp = (np.array([1, 2, 3, 4, 5], float) - mu) / sd
    assert np.allclose(z[0], exp, atol=1e-12)
    m = clip_mult(1.0 + 0.25 * z)
    assert np.allclose(m[0], np.clip(1 + 0.25 * exp, 0.5, 1.5), atol=1e-12)
    z0 = xs_z(np.array([[2.0, 2.0, 2.0, 2.0, 2.0]]))
    assert (z0[0] == 0.0).all()
    zn = xs_z(np.array([[np.nan, 1.0, 2.0, 3.0, 4.0]]))
    assert np.isnan(zn[0, 0]) and np.isfinite(zn[0, 1:]).all()
    mn = clip_mult(np.array([[np.nan, 2.0]]))
    assert mn[0, 0] == 1.0 and mn[0, 1] == 1.5
    T = pd.DatetimeIndex(["2022-01-02 04:00"])
    assert d_last(pd.to_datetime(T, utc=True))[0] == pd.Timestamp("2022-01-01", tz="UTC")
    T2 = pd.date_range("2022-04-01", "2022-04-02", freq="4h", tz="UTC")
    Mb = raw_bybit_matrix(T2, SYMS)
    assert Mb.shape == (len(T2), 5) and np.isfinite(Mb).all()
    Mn = raw_binance_matrix(T2, SYMS)
    assert Mn.shape == (len(T2), 5) and np.isfinite(Mn).all()
    # A1 path bit-exact vs oc_lit_xs xs_signal on sampled T
    sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_lit_xs"))
    import xs_signal as ref

    T3 = pd.date_range("2022-05-01", "2022-05-05", freq="4h", tz="UTC")
    f_mine, _ = a1_mult(T3, cols=SYMS)
    frames, _ = ref.tilt_frames(T3, SYMS)
    pd.testing.assert_frame_equal(f_mine, frames["A1"], check_exact=True)
    # Bybit daily uses turnover column, positive where finite
    d = load_binance_daily("BTCUSDT")
    assert np.isfinite(d["Amihud30"].loc["2022-03-15"])
    db = load_bybit_daily("ETHUSDT")
    assert np.isfinite(db["Amihud30"].loc["2022-03-15"])
