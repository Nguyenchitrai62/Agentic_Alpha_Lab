"""oc_stablegate tests: causality/truncation + hand-checked synthetic cases (PLAN-fixed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(HERE).parents[0] / "research" / "tournament" / "oc_stablegate"))
from stablegate_signal import asof_z, dip_mult, gate_mult, load_daily


def test_signal_truncation_causal():
    """z(D) recomputed from caps truncated to <= D is unchanged; asof z(T) uses only avail <= T."""
    daily = load_daily()
    # Sample a mid-history day with finite z.
    fin = daily[np.isfinite(daily["z"])]
    D0 = fin.index[len(fin) // 2]
    # Recompute impulse/z at D0 from caps <= D0 only.
    caps = daily["cap"].loc[:D0]
    imp = np.log(float(caps.loc[D0]) / float(caps.shift(30).loc[D0]))
    W = np.log((caps / caps.shift(30)).dropna()).iloc[-730:]
    W = W.loc[:D0].iloc[-730:]
    assert len(W) >= 365
    mu, sd = float(W.mean()), float(W.std(ddof=1))
    z_trunc = (imp - mu) / sd
    assert np.isfinite(z_trunc)
    assert abs(z_trunc - float(daily.loc[D0, "z"])) < 1e-9
    # asof truncation: T just after D0's avail sees D0; just before does not.
    avail = daily.loc[D0, "avail"]
    z_at = asof_z(daily, pd.DatetimeIndex([avail]))[0]
    z_before = asof_z(daily, pd.DatetimeIndex([avail - pd.Timedelta(seconds=1)]))[0]
    assert abs(z_at - float(daily.loc[D0, "z"])) < 1e-12
    # The value just before must equal the previous day's z (or NaN), never D0's future.
    prev = daily["z"].loc[:D0].iloc[:-1]
    prev = prev[np.isfinite(prev)]
    if len(prev):
        assert abs(z_before - float(prev.iloc[-1])) < 1e-12 or np.isnan(z_before)


def test_handchecked_synthetic():
    """Hand-checked impulse, boundary multipliers, and availability mapping."""
    # 1. impulse: cap 100 -> 130 over 30 days = log(1.3).
    assert abs(np.log(130.0 / 100.0) - 0.26236426446749106) < 1e-12
    # 2. Book-gate boundaries (strict <): -1.0 is NOT gated, just below IS.
    z = np.array([-2.0, -1.5, -1.0001, -1.0, -0.9, 0.0])
    m1 = gate_mult(z, -1.0)
    assert list(m1) == [0.75, 0.75, 0.75, 1.0, 1.0, 1.0]
    m15 = gate_mult(z, -1.5)
    assert list(m15) == [0.75, 1.0, 1.0, 1.0, 1.0, 1.0]  # strict <: -1.5 not gated
    # NaN -> 1.
    assert list(gate_mult(np.array([np.nan]), -1.0)) == [1.0]
    # 3. Dip dial boundaries (strict > / <): +/-1.0 exactly -> x1.
    zd = np.array([1.0001, 1.0, 0.0, -1.0, -1.0001])
    up, dn = 0.32 / 0.26, 0.20 / 0.26
    assert list(dip_mult(zd, "D1")) == [up, 1.0, 1.0, 1.0, dn]
    assert list(dip_mult(zd, "D2")) == [up, 1.0, 1.0, 1.0, 1.0]
    assert abs(up - 1.2307692307692308) < 1e-12
    assert abs(dn - 0.7692307692307693) < 1e-12
    # 4. Availability mapping: D usable from D+1 04:00.
    days = pd.date_range("2022-01-01", periods=3, freq="D", tz="UTC")
    synth = pd.DataFrame({"z": [10.0, 20.0, 30.0], "avail": days + pd.Timedelta(hours=28)},
                         index=days)
    T = pd.DatetimeIndex(["2022-01-02 03:59:59+00:00", "2022-01-02 04:00:00+00:00",
                          "2022-01-03 04:00:00+00:00", "2022-01-04 04:00:00+00:00"], tz="UTC")
    got = asof_z(synth, T)
    # avail(D=01-01)=01-02 04:00 (z=10); avail(01-02)=01-03 04:00 (z=20); avail(01-03)=01-04 04:00 (z=30).
    assert np.isnan(got[0]) and list(got[1:]) == [10.0, 20.0, 30.0]
    # Before any avail -> NaN.
    assert np.isnan(asof_z(synth, pd.DatetimeIndex(["2022-01-01 00:00+00:00"]))[0])
