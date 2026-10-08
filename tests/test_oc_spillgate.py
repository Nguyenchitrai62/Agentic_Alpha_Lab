"""oc_spillgate tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
SP = ROOT / "research/tournament/oc_spillgate"
sys.path.insert(0, str(SP))

from spill_rule import ANCH5, anchor_of, control_mult, gate_change, gate_level, pairwise_mean_corr


def test_pairwise_handchecked():
    # perfect co-movement -> 1.0
    t = np.arange(6, dtype=float)
    R = np.column_stack([t, 2 * t + 1, -t, t ** 2 * 0 + t, t * 0.5])
    # cols 0,1,3,4 perfectly correlated (+1), col2 perfectly anti (-1)
    # mean over 10 pairs: pairs among {0,1,3,4} = 6 pairs at +1;
    # pairs with col2 = 4 pairs at -1 -> mean (6-4)/10 = 0.2
    assert pairwise_mean_corr(R) == abs(pairwise_mean_corr(R))
    assert abs(pairwise_mean_corr(R) - 0.2) < 1e-12
    # zero-variance leg -> those pairs NaN; remaining 6 pairs of 4 live cols
    R0 = R.copy()
    R0[:, 4] = 1.0
    # valid pairs = 6 (among cols 0,1,2,3): 3x(+1) + 3x(-1) -> 0.0; still >=8? No:
    # pairs involving col4 = 4 NaN -> only 6 valid < 8 -> NaN
    assert not np.isfinite(pairwise_mean_corr(R0))
    # all identical -> every pair +1 -> 1.0
    R1 = np.column_stack([t, t, t, t, t])
    assert abs(pairwise_mean_corr(R1) - 1.0) < 1e-12
    # insufficient overlap -> NaN
    Rn = np.full((6, 5), np.nan)
    Rn[:2, :] = 1.0
    assert not np.isfinite(pairwise_mean_corr(Rn))


def test_gate_strict_and_nan():
    assert gate_level(0.5, 0.4) is True
    assert gate_level(0.4, 0.4) is False  # strict
    assert gate_level(np.nan, 0.4) is False
    assert gate_level(0.5, np.nan) is False
    assert gate_change(0.1, 0.05) is True
    assert gate_change(0.05, 0.05) is False
    assert gate_change(np.nan, 0.05) is False


def test_control_mult_handchecked():
    assert control_mult(0.0) == 1.0
    assert abs(control_mult(0.10) - 0.95) < 1e-12
    assert control_mult(1.0) == 0.5


def test_anchor_of_boundaries():
    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    ns = np.array([a.value for a in anch], dtype=np.int64)
    T = np.array([
        pd.Timestamp("2020-01-01", tz="UTC").value,  # before first -> 0
        pd.Timestamp("2021-09-24", tz="UTC").value,  # exactly A0 -> 0
        pd.Timestamp("2023-09-24", tz="UTC").value,  # exactly A2 -> 2
        pd.Timestamp("2026-09-23", tz="UTC").value,  # in year 4 -> 4
        pd.Timestamp("2030-01-01", tz="UTC").value,  # after last -> 4
    ], dtype=np.int64)
    assert list(anchor_of(T, ns)) == [0, 0, 2, 4, 4]


def _synth_hourly():
    """Synthetic hourly closes for 5 majors over 40 days (causal test panel)."""
    rng = np.random.default_rng(7)
    starts = pd.date_range("2021-01-01", periods=40 * 24, freq="h", tz="UTC")
    rows = []
    for j, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]):
        px = 100 + np.cumsum(rng.normal(0, 0.002, len(starts))) + j * 0.001
        rows.append(pd.DataFrame({"t": starts, "close": np.exp(px), "sym": sym}))
    return pd.concat(rows, ignore_index=True)


def test_causality_truncation_synthetic():
    """Truncating hourly input to <= T0 cannot change c/d rows at T <= T0."""
    from compute_spill import GRID_END, GRID_START, build_4h_closes, compute_cd
    h = _synth_hourly()
    c4 = build_4h_closes(h)
    cd = compute_cd(c4)
    T0 = pd.Timestamp("2021-01-20 12:00", tz="UTC")
    # hourly bars with END <= T0  <=> start < T0
    ht = h[pd.to_datetime(h["t"], utc=True) < T0].copy()
    c4t = build_4h_closes(ht)
    cdt = compute_cd(c4t)
    keep = cd[cd["T"] <= T0].reset_index(drop=True)
    keept = cdt[cdt["T"] <= T0].reset_index(drop=True)
    assert len(keep) and len(keep) == len(keept)
    assert np.allclose(keep["c"].to_numpy(), keept["c"].to_numpy(), equal_nan=True)
    assert np.allclose(keep["d"].to_numpy(), keept["d"].to_numpy(), equal_nan=True)


def test_no_future_hour_synthetic():
    """c(T) for a bar never uses an hourly bar ending after T (spike test)."""
    from compute_spill import build_4h_closes, compute_cd
    starts = pd.date_range("2021-03-01", periods=30 * 24, freq="h", tz="UTC")
    rows = []
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]:
        rows.append(pd.DataFrame({"t": starts, "close": 100.0, "sym": sym}))
    h = pd.concat(rows, ignore_index=True)
    # inject a one-hour +50% spike in ALL coins at 2021-03-15 10:00 (END 11:00)
    spike_start = pd.Timestamp("2021-03-15 10:00", tz="UTC")
    m = pd.to_datetime(h["t"], utc=True) == spike_start
    h.loc[m, "close"] = 150.0
    c4 = build_4h_closes(h)
    cd = compute_cd(c4)
    # last T with all-6-returns clean must precede the spike's first affected 4h bar
    # the 4h bar ending 2021-03-15 12:00 contains the spike -> c there may move,
    # but every c row at T <= 2021-03-15 08:00 must equal the flat-panel value (NaN
    # here: zero variance -> NaN, i.e. definitely not moved by the future spike)
    pre = cd[cd["T"] <= pd.Timestamp("2021-03-15 08:00", tz="UTC")]
    assert len(pre) > 5
    assert bool((~np.isfinite(pre["c"].to_numpy())).all())


def test_real_norm_windows_embargoed():
    """Stored thresholds equal embargoed-window quantiles (if computed)."""
    import json
    th = SP / "tmp/thresholds.json"
    cd_p = SP / "tmp/cd_std.parquet"
    if not (th.exists() and cd_p.exists()):
        import pytest
        pytest.skip("gates not computed yet")
    thresholds = json.loads(th.read_text())
    cd = pd.read_parquet(cd_p)
    T = pd.to_datetime(cd["T"], utc=True)
    for a in ANCH5:
        A = pd.Timestamp(a, tz="UTC")
        m = (T >= A - pd.Timedelta(days=372)) & (T < A - pd.Timedelta(days=7))
        pc = cd.loc[m, "c"].to_numpy(dtype=float)
        pc = pc[np.isfinite(pc)]
        assert len(pc) >= 1000
        assert abs(float(np.quantile(pc, 0.90)) - thresholds[a]["q90"]) < 1e-12
