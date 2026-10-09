"""oc_lit_xs tests: causality/truncation + hand-checked synthetic cases (PLAN-fixed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(Path(HERE).parents[0] / "research" / "tournament" / "oc_lit_xs"))
from xs_signal import (clip_mult, d_last, load_daily, tilt_frames, variant_mult_frame,
                       xs_z, xs_z_tercile)


def test_signal_truncation_causal():
    """Amihud30/MAX21 at D0 from data truncated to <= D0 match; T-mapping uses only closed days."""
    d = load_daily("BTCUSDT")
    fin = d[np.isfinite(d["Amihud30"]) & np.isfinite(d["MAX21"])]
    D0 = fin.index[len(fin) // 2]
    # Truncated recompute from closes/quote_volumes <= D0 only.
    sub = d.loc[:D0, ["close", "quote_volume"]]
    r = sub["close"] / sub["close"].shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        am = r.abs() / sub["quote_volume"]
    am[(~np.isfinite(r)) | ~(sub["quote_volume"] > 0)] = np.nan
    ami_tr = float(am.iloc[-30:].mean()) if am.iloc[-30:].notna().sum() >= 20 else np.nan
    max_tr = float(r.iloc[-21:].max()) if r.iloc[-21:].notna().sum() >= 15 else np.nan
    assert np.isfinite(ami_tr) and abs(ami_tr - float(d.loc[D0, "Amihud30"])) < 1e-12
    assert np.isfinite(max_tr) and abs(max_tr - float(d.loc[D0, "MAX21"])) < 1e-12
    # D*(T): T at D0+1 00:00 sees D0; 1s before does not.
    T_at = pd.DatetimeIndex([D0 + pd.Timedelta(days=1)], tz="UTC")
    T_before = pd.DatetimeIndex([D0 + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)], tz="UTC")
    assert d_last(T_at)[0] == D0
    assert d_last(T_before)[0] == D0 - pd.Timedelta(days=1)
    # Sampled-T truncation: multipliers at T from full index equal those from truncated index.
    Tfull = pd.date_range("2022-03-01", periods=9, freq="4h", tz="UTC")
    cols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    f_full, _ = tilt_frames(Tfull, cols)
    f_tr, _ = tilt_frames(Tfull[:5], cols)
    for v in f_full:
        assert np.allclose(f_full[v].to_numpy()[:5], f_tr[v].to_numpy(), equal_nan=True)


def test_handchecked_synthetic():
    """Hand-checked z, terciles, clip, variant maths and availability mapping."""
    # 1. XS z: [1,2,3,4,5] -> mean 3, std ddof=1 sqrt(2.5).
    m = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
    z = xs_z(m)
    sd = np.std([1, 2, 3, 4, 5], ddof=1)
    assert abs(sd - 1.5811388300841898) < 1e-12
    assert np.allclose(z[0], (m[0] - 3.0) / sd)
    # Zero-spread -> 0; NaN raw -> NaN z.
    assert list(xs_z(np.array([[2.0, 2.0, 2.0]]))[0]) == [0.0, 0.0, 0.0]
    zn = xs_z(np.array([[1.0, np.nan, 3.0]]))[0]
    assert np.isnan(zn[1]) and abs(zn[0] + zn[2]) < 1e-12
    # 2. Terciles: sizes [10,20,30,40,50] -> groups {10,20},{30,40},{50};
    # ami [1,3,2,4,9]: g0 z = (-0.7071,+0.7071), g1 = (-0.7071,+0.7071), g2 = 0.
    ami = np.array([[1.0, 3.0, 2.0, 4.0, 9.0]])
    siz = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])
    zt = xs_z_tercile(ami, siz)
    assert np.allclose(zt[0, :4], [-0.7071067811865476, 0.7071067811865476,
                                  -0.7071067811865476, 0.7071067811865476])
    assert zt[0, 4] == 0.0
    # 3. Clip: NaN->1, extremes clipped.
    assert list(clip_mult(np.array([np.nan, 0.1, 2.0, 1.0]))) == [1.0, 0.5, 1.5, 1.0]
    # 4. Variant maths on z=[-2,-1,0,1,2] (K=0.25): A1=1+0.25z, X3=1-0.25z, A2 floors at 1.
    zi = np.array([[-2.0, -1.0, 0.0, 1.0, 2.0]])
    zt0 = zi.copy()
    zm = zi.copy()
    a1 = variant_mult_frame(zi, zt0, zm, "A1")[0]
    assert np.allclose(a1, [0.5, 0.75, 1.0, 1.25, 1.5])
    a2 = variant_mult_frame(zi, zt0, zm, "A2")[0]
    assert np.allclose(a2, [1.0, 1.0, 1.0, 1.25, 1.5])
    x3 = variant_mult_frame(zi, zt0, zm, "X3")[0]
    assert np.allclose(x3, [1.5, 1.25, 1.0, 0.75, 0.5])
    # 5. Availability: T at midnight sees prior day, never the current day.
    T = pd.DatetimeIndex(["2022-01-02 00:00+00:00", "2022-01-02 04:00+00:00"], tz="UTC")
    assert list(d_last(T)) == [pd.Timestamp("2022-01-01", tz="UTC")] * 2
    # 6. Amihud hand-check: |r|=0.02, quote=1e6 -> 2e-8.
    assert abs(0.02 / 1e6 - 2e-8) < 1e-20
