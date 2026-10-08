"""oc_btcresid tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
SP = ROOT / "research/tournament/oc_btcresid"
sys.path.insert(0, str(SP))

from resid_rule import (ANCH5, anchor_of, beta_for_use, clip01, control_mult,
                        ols_beta, resid_frame, resid_row)


def test_ols_beta_handchecked():
    # y = 2x + 1 exactly -> slope 2
    x = np.arange(1, 200, dtype=float)
    y = 2 * x + 1
    assert abs(ols_beta(x, y) - 2.0) < 1e-12
    # y = -0.5x -> slope -0.5
    assert abs(ols_beta(x, -0.5 * x) + 0.5) < 1e-12
    # zero-variance x -> NaN
    assert not np.isfinite(ols_beta(np.ones(200), np.arange(200, dtype=float)))
    # too few pairs -> NaN
    assert not np.isfinite(ols_beta(np.array([1.0, 2.0]), np.array([1.0, 2.0])))
    # NaN-tolerant: 150 finite of 200 still fine
    xx = x.copy()
    xx[:50] = np.nan
    assert abs(ols_beta(xx, 2 * x + 1) - 2.0) < 1e-10


def test_clip_and_use():
    assert clip01(-0.5) == 0.0
    assert clip01(1.5) == 1.0
    assert clip01(0.7) == 0.7
    assert clip01(float("nan")) == 0.0
    assert beta_for_use(float("nan"), False) == 0.0
    assert beta_for_use(float("nan"), True) == 0.0
    assert beta_for_use(1.7, False) == 1.7
    assert beta_for_use(1.7, True) == 1.0
    assert beta_for_use(-0.3, True) == 0.0
    assert beta_for_use(-0.3, False) == -0.3


def test_resid_row_handchecked():
    # w_c=0.10, wBTC=0.20, beta=0.5 -> 0.10-0.10=0.0
    assert abs(resid_row(0.10, 0.20, 0.5) - 0.0) < 1e-12
    # V2 clips beta 1.7 -> 1.0: 0.10-0.20=-0.10
    assert abs(resid_row(0.10, 0.20, 1.7, clip=True) + 0.10) < 1e-12
    # V1 raw keeps 1.7: 0.10-0.34=-0.24
    assert abs(resid_row(0.10, 0.20, 1.7, clip=False) + 0.24) < 1e-12
    # BTC leg: w-w*1 = 0
    assert abs(resid_row(0.20, 0.20, 1.0) - 0.0) < 1e-12


def test_resid_frame_zeroes_btc():
    idx = pd.date_range("2022-01-01", periods=3, freq="4h", tz="UTC")
    sb = pd.DataFrame({"BTCUSDT": [0.2, -0.1, 0.0],
                       "ETHUSDT": [0.1, 0.05, 0.03],
                       "SOLUSDT": [0.0, 0.0, 0.0],
                       "BNBUSDT": [0.05, 0.05, 0.05],
                       "XRPUSDT": [-0.05, -0.05, -0.05]}, index=idx)
    betas = {"ETHUSDT": 0.5, "SOLUSDT": 1.7, "BNBUSDT": -0.3, "XRPUSDT": float("nan")}
    v1 = resid_frame(sb, betas, clip=False)
    # BTC leg is exactly zero
    assert bool((v1["BTCUSDT"] == 0.0).all())
    # ETH: 0.10-0.5*0.20 = 0.0
    assert abs(float(v1["ETHUSDT"].iloc[0]) - 0.0) < 1e-12
    # SOL V1 raw: 0.0-1.7*0.2 = -0.34
    assert abs(float(v1["SOLUSDT"].iloc[0]) + 0.34) < 1e-12
    # BNB V1 raw negative beta adds: 0.05-(-0.3*0.2)=0.11
    assert abs(float(v1["BNBUSDT"].iloc[0]) - 0.11) < 1e-12
    # NaN beta -> unchanged: -0.05
    assert abs(float(v1["XRPUSDT"].iloc[0]) + 0.05) < 1e-12
    v2 = resid_frame(sb, betas, clip=True)
    assert abs(float(v2["SOLUSDT"].iloc[0]) + 0.20) < 1e-12  # clipped to 1.0
    assert abs(float(v2["BNBUSDT"].iloc[0]) - 0.05) < 1e-12  # clipped to 0.0
    assert abs(float(v2["XRPUSDT"].iloc[0]) + 0.05) < 1e-12


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


def test_control_mult_handchecked():
    assert control_mult(0.8, 1.0) == 0.8
    assert control_mult(0.0, 1.0) == 0.0
    assert control_mult(1.0, 0.0) == 1.0  # degenerate ref -> 1.0
    assert control_mult(float("nan"), 1.0) == 1.0


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
    """Truncating hourly input to < T0 cannot change returns rows at T <= T0."""
    from compute_beta import build_4h_closes, compute_rets
    h = _synth_hourly()
    c4 = build_4h_closes(h)
    rr = compute_rets(c4)
    T0 = pd.Timestamp("2021-01-20 12:00", tz="UTC")
    ht = h[pd.to_datetime(h["t"], utc=True) < T0].copy()
    c4t = build_4h_closes(ht)
    rrt = compute_rets(c4t)
    keep = rr[rr.index <= T0]
    keept = rrt[rrt.index <= T0]
    assert len(keep) and len(keep) == len(keept)
    assert np.allclose(keep.to_numpy(), keept.to_numpy(), equal_nan=True)


def test_no_future_hour_synthetic():
    """A future hourly spike never moves returns at T <= spike close."""
    from compute_beta import build_4h_closes, compute_rets
    starts = pd.date_range("2021-03-01", periods=30 * 24, freq="h", tz="UTC")
    rows = []
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]:
        rows.append(pd.DataFrame({"t": starts, "close": 100.0, "sym": sym}))
    h = pd.concat(rows, ignore_index=True)
    spike_start = pd.Timestamp("2021-03-15 10:00", tz="UTC")
    m = pd.to_datetime(h["t"], utc=True) == spike_start
    h.loc[m, "close"] = 150.0
    c4 = build_4h_closes(h)
    rr = compute_rets(c4)
    # the 4h bar ending 2021-03-15 12:00 contains the spike; every return row
    # at T <= 2021-03-15 08:00 must be untouched by the future spike: NaN where
    # the grid predates the synthetic hourly start, else exactly 0.0 (flat panel).
    pre = rr[rr.index <= pd.Timestamp("2021-03-15 08:00", tz="UTC")]
    assert len(pre) > 5
    vals = pre.to_numpy()
    assert bool(((vals == 0.0) | np.isnan(vals)).all())
    assert bool((vals[~np.isnan(vals)] == 0.0).all())


def test_beta_embargo_uses_only_window():
    """Stored betas equal embargoed-window OLS (if computed)."""
    import json
    bp = SP / "tmp/betas.json"
    rp = SP / "tmp/rets_std.parquet"
    if not (bp.exists() and rp.exists()):
        import pytest
        pytest.skip("betas not computed yet")
    betas = json.loads(bp.read_text())["betas"]
    rets = pd.read_parquet(rp)
    T = rets.index
    for a in ANCH5:
        A = pd.Timestamp(a, tz="UTC")
        m = (T >= A - pd.Timedelta(days=372)) & (T < A - pd.Timedelta(days=7))
        for c in ["ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]:
            b = ols_beta(rets.loc[m, "BTCUSDT"].to_numpy(),
                         rets.loc[m, c].to_numpy())
            stored = float(betas[a][c])
            if np.isfinite(b):
                assert abs(stored - b) < 1e-12
            else:
                assert not np.isfinite(stored)
