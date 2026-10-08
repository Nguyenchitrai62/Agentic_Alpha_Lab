"""oc_volvolbrake tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
SP = ROOT / "research/tournament/oc_volvolbrake"
sys.path.insert(0, str(SP))

from volvol_rule import ANCH5, anchor_of, control_mult, fragility_from_daily, gate_level, rv6_from_returns


def test_rv6_handchecked():
    R = np.array([0.01, -0.02, 0.015, -0.005, 0.02, -0.01])
    assert abs(rv6_from_returns(R) - float(np.std(R, ddof=1))) < 1e-12
    assert not np.isfinite(rv6_from_returns(np.array([0.01, np.nan, 0.01, 0.01, 0.01, 0.01])))
    assert not np.isfinite(rv6_from_returns(np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])) + np.nan)


def test_fragility_handchecked():
    D = np.arange(30, dtype=float)
    assert abs(fragility_from_daily(D) - float(np.std(D, ddof=1))) < 1e-12
    Dn = D.copy()
    Dn[5] = np.nan
    assert not np.isfinite(fragility_from_daily(Dn))
    # constant daily RV -> zero fragility (finite 0.0)
    assert fragility_from_daily(np.ones(30)) == 0.0


def test_gate_strict_and_nan():
    assert gate_level(0.5, 0.4) is True
    assert gate_level(0.4, 0.4) is False  # strict
    assert gate_level(np.nan, 0.4) is False
    assert gate_level(0.5, np.nan) is False


def test_control_mult_handchecked():
    assert control_mult(0.0) == 1.0
    assert abs(control_mult(0.10) - 0.95) < 1e-12
    assert control_mult(1.0) == 0.5


def test_anchor_of_boundaries():
    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    ns = np.array([a.value for a in anch], dtype=np.int64)
    T = np.array([
        pd.Timestamp("2020-01-01", tz="UTC").value,
        pd.Timestamp("2021-09-24", tz="UTC").value,
        pd.Timestamp("2023-09-24", tz="UTC").value,
        pd.Timestamp("2026-09-23", tz="UTC").value,
        pd.Timestamp("2030-01-01", tz="UTC").value,
    ], dtype=np.int64)
    assert list(anchor_of(T, ns)) == [0, 0, 2, 4, 4]


def _synth_hourly():
    rng = np.random.default_rng(11)
    starts = pd.date_range("2021-01-01", periods=70 * 24, freq="h", tz="UTC")
    px = 100 + np.cumsum(rng.normal(0, 0.002, len(starts)))
    return pd.DataFrame({"t": starts, "close": np.exp(px), "sym": "BTCUSDT"})


def test_causality_truncation_synthetic():
    """Truncating hourly input to bars ending <= T0 cannot change f rows at T <= T0."""
    from compute_volvol import build_4h_closes_btc, compute_rvf
    h = _synth_hourly()
    c4 = build_4h_closes_btc(h)
    rdf = compute_rvf(c4)
    T0 = pd.Timestamp("2021-02-20 12:00", tz="UTC")
    ht = h[pd.to_datetime(h["t"], utc=True) < T0].copy()
    c4t = build_4h_closes_btc(ht)
    rdft = compute_rvf(c4t)
    keep = rdf[rdf["T"] <= T0].reset_index(drop=True)
    keept = rdft[rdft["T"] <= T0].reset_index(drop=True)
    assert len(keep) and len(keep) == len(keept)
    assert np.allclose(keep["rv6"].to_numpy(), keept["rv6"].to_numpy(), equal_nan=True)
    assert np.allclose(keep["f"].to_numpy(), keept["f"].to_numpy(), equal_nan=True)


def test_no_future_hour_synthetic():
    """f(T) for a bar never uses an hourly bar ending after the prior day (spike test)."""
    from compute_volvol import build_4h_closes_btc, compute_rvf
    starts = pd.date_range("2021-03-01", periods=70 * 24, freq="h", tz="UTC")
    h = pd.DataFrame({"t": starts, "close": 100.0, "sym": "BTCUSDT"})
    spike_start = pd.Timestamp("2021-04-10 10:00", tz="UTC")
    h.loc[pd.to_datetime(h["t"], utc=True) == spike_start, "close"] = 150.0
    c4 = build_4h_closes_btc(h)
    rdf = compute_rvf(c4)
    # f is constant within a day and uses days strictly before; on the flat panel
    # RV6 == 0 so f == 0.0 after warm-up. No pre-spike f row may be moved by the
    # future spike: finite pre-spike f must all equal 0.0.
    pre = rdf[rdf["T"] <= pd.Timestamp("2021-04-10 00:00", tz="UTC")]
    assert len(pre) > 30
    finite = pre["f"].to_numpy()[np.isfinite(pre["f"].to_numpy())]
    assert len(finite) > 0
    assert bool((finite == 0.0).all())


def test_real_norm_windows_embargoed():
    """Stored thresholds equal embargoed-window quantiles (if computed)."""
    import json
    th = SP / "tmp/thresholds.json"
    rv_p = SP / "tmp/rvf_std.parquet"
    if not (th.exists() and rv_p.exists()):
        import pytest
        pytest.skip("gates not computed yet")
    thresholds = json.loads(th.read_text())
    rdf = pd.read_parquet(rv_p)
    T = pd.to_datetime(rdf["T"], utc=True)
    f = rdf["f"].to_numpy(dtype=float)
    for a in ANCH5:
        A = pd.Timestamp(a, tz="UTC")
        m = (T >= A - pd.Timedelta(days=372)) & (T < A - pd.Timedelta(days=7))
        pf = f[m]
        pf = pf[np.isfinite(pf)]
        assert len(pf) >= 1000
        assert abs(float(np.quantile(pf, 0.90)) - thresholds[a]["q90"]) < 1e-12
        assert abs(float(np.quantile(pf, 0.85)) - thresholds[a]["q85"]) < 1e-12
