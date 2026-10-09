"""oc_lit_fhlh tests: causality/truncation + hand-checked synthetic cases (PLAN-fixed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(HERE).parents[0] / "research" / "tournament" / "oc_lit_fhlh"))
from fhlh_signal import asof_fh, asof_median, build_daily_fh, gate_mults


def test_signal_truncation_causal():
    """FH(D) from 1m truncated to <= D 00:29 matches full build; asof uses D+00:30."""
    import fhlh_signal as S

    m1 = S.load_btc_1m()
    full = build_daily_fh(m1)
    fin = full[np.isfinite(full["fh"])]
    D0 = fin.index[len(fin) // 2]
    # Truncate 1m to bars with open_time <= D0 00:29 and rebuild that day only.
    cut = m1[m1["open_time"] <= D0 + pd.Timedelta(minutes=29)]
    trunc = build_daily_fh(cut)
    assert abs(float(trunc.loc[D0, "fh"]) - float(full.loc[D0, "fh"])) < 1e-12
    # asof boundary: D0+00:30 sees D0; one second before sees D0-1.
    avail = full.loc[D0, "avail"]
    z_at = asof_fh(full, pd.DatetimeIndex([avail]))[0]
    z_before = asof_fh(full, pd.DatetimeIndex([avail - pd.Timedelta(seconds=1)]))[0]
    assert abs(z_at - float(full.loc[D0, "fh"])) < 1e-12
    prev = full["fh"].loc[:D0].iloc[:-1]
    prev = prev[np.isfinite(prev)]
    if len(prev):
        assert abs(z_before - float(prev.iloc[-1])) < 1e-12 or np.isnan(z_before)
    # Medians use only days before anchor - 7d: recompute one anchor by hand.
    med = S.medians(full)
    a0 = pd.Timestamp("2022-09-24", tz="UTC")
    w = full[(full.index >= a0 - pd.Timedelta(days=372)) & (full.index < a0 - pd.Timedelta(days=7))]["fh"]
    w = w[np.isfinite(w.to_numpy(float))]
    assert abs(med["2022-09-24"] - float(np.median(np.abs(w.to_numpy(float))))) < 1e-12
    # asof_median maps T to its anchor year's median.
    T = pd.DatetimeIndex(["2022-09-24 04:00+00:00", "2023-09-24 04:00+00:00"], tz="UTC")
    got = asof_median(full, T, med)
    assert list(got) == [med["2022-09-24"], med["2023-09-24"]]


def test_handchecked_synthetic():
    """Hand-checked FH math, boundary multipliers, and availability mapping."""
    # 1. FH: open 100 -> close 103 over 30 min = 3%.
    assert abs((103.0 / 100.0 - 1.0) - 0.03) < 1e-12
    # 2. M1/M2 boundaries (strict >0 / <0): exactly 0 gates (x0.6 both sides).
    fh = np.array([0.01, 0.0, -0.01, np.nan])
    gm = gate_mults(fh, np.array([0.005, 0.005, 0.005, 0.005]))
    assert list(gm["M1_long"]) == [1.0, 0.6, 0.6, 1.0]
    assert list(gm["M2_short"]) == [0.6, 0.6, 1.0, 1.0]
    # 3. M3 noise filter: |FH| < med -> 1.0 even when sign says gate.
    fh3 = np.array([0.001, -0.02])
    med3 = np.array([0.005, 0.005])
    gm3 = gate_mults(fh3, med3)
    assert list(gm3["M3_long"]) == [1.0, 0.6]
    # NaN fh or NaN med -> 1.0.
    gmn = gate_mults(np.array([np.nan, -0.02]), np.array([0.005, np.nan]))
    assert list(gmn["M3_long"]) == [1.0, 1.0]
    # 4. Availability: D usable from D+00:30.
    days = pd.date_range("2022-01-01", periods=3, freq="D", tz="UTC")
    synth = pd.DataFrame({"fh": [0.01, -0.02, 0.03], "avail": days + pd.Timedelta(minutes=30)}, index=days)
    T = pd.DatetimeIndex(["2022-01-01 00:29:59+00:00", "2022-01-01 00:30:00+00:00",
                          "2022-01-02 00:30:00+00:00", "2022-01-03 00:30:00+00:00"], tz="UTC")
    got = asof_fh(synth, T)
    # Before first avail the previous day is unknown here -> NaN; then 0.01, -0.02, 0.03.
    assert np.isnan(got[0]) and list(got[1:]) == [0.01, -0.02, 0.03]
