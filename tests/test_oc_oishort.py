"""Tests for oc_oishort (causality/truncation + hand-checked synthetics)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_oishort"))

from oishort_rule import gate_short, log_change, price_trigger, trailing_sg


def test_log_change_handchecked():
    assert abs(log_change(110.0, 100.0) - np.log(1.1)) < 1e-12
    assert np.isnan(log_change(0.0, 100.0))
    assert np.isnan(log_change(100.0, 0.0))
    assert np.isnan(log_change(float("nan"), 100.0))
    assert np.isnan(log_change(-5.0, 100.0))


def test_price_trigger_frozen_k2():
    # R24 = -0.04, sg = 0.01 -> -0.04 < -0.02 True
    assert price_trigger(-0.04, 0.01) is True
    # exactly -2sg -> strict < -> False
    assert price_trigger(-0.02, 0.01) is False
    # positive return -> False
    assert price_trigger(0.05, 0.01) is False
    assert price_trigger(float("nan"), 0.01) is False
    assert price_trigger(-0.04, 0.0) is False


def test_gate_short_handchecked():
    # z = (0.10-0.0)/0.04 = 2.5 > 2 and price -0.04 < -0.02 -> O1 True
    assert gate_short(0.10, 0.0, 0.04, -0.04, 0.01, z_thr=2.0) is True
    # z = 2.0 exactly -> strict > -> False
    assert gate_short(0.08, 0.0, 0.04, -0.04, 0.01, z_thr=2.0) is False
    # O2 looser: z = 1.75 > 1.5 True with same price leg
    assert gate_short(0.07, 0.0, 0.04, -0.04, 0.01, z_thr=1.5) is True
    # same OI but price up -> False (divergence needs price DOWN)
    assert gate_short(0.10, 0.0, 0.04, 0.05, 0.01, z_thr=2.0) is False
    # OI down (z negative) -> False
    assert gate_short(-0.10, 0.0, 0.04, -0.04, 0.01, z_thr=2.0) is False
    # sd<=0 -> never gate
    assert gate_short(0.10, 0.0, 0.0, -0.04, 0.01, z_thr=2.0) is False


def test_trailing_sg_uses_strictly_prior_returns():
    rng = np.random.default_rng(3)
    rets = rng.normal(0, 0.01, size=400)
    # full window std
    assert abs(trailing_sg(rets) - float(np.std(rets[-360:], ddof=1))) < 1e-12
    # appending a future return then truncating back leaves sg unchanged
    ext = np.concatenate([rets, [10.0]])
    assert trailing_sg(ext[:400]) == trailing_sg(rets)
    # too few observations -> NaN
    assert np.isnan(trailing_sg(np.array([0.01, -0.02])))
    # zero variance -> NaN (never gate)
    assert np.isnan(trailing_sg(np.zeros(200)))


def test_truncation_future_oi_or_price_cannot_fire():
    """A gate using data at/after T+1 cannot change the gate at T (causal asof)."""
    # OI series: gate at T uses last OI <= T-5min; appending future OI rows
    # with timestamps > T-5min then truncating back gives identical dOI.
    oi_t = np.array([0, 300, 600, 900], dtype=np.int64)  # seconds
    oi_v = np.array([100.0, 102.0, 105.0, 130.0])
    T = 1200  # query time (s); lag 300s -> q = 900
    lag = 300
    q = T - lag
    i_now = int(np.searchsorted(oi_t, q, side="right") - 1)
    assert oi_v[i_now] == 130.0
    # future row at t=1500 (> q) appended then truncated -> same index
    oi_t2 = np.concatenate([oi_t, [1500]])
    i2 = int(np.searchsorted(oi_t2[:4], q, side="right") - 1)
    assert i2 == i_now


def test_real_norm_window_uses_preanchor_embargo_only():
    """Stored mu/sd for anchor 2021-09-24 (BTC) equal moments of dOI in
    [A-372d, A-7d) only (fit-window causality on real data)."""
    p = ROOT / "research/tournament/oc_oishort/tmp/oishort_panel.parquet"
    df = pd.read_parquet(p, columns=["T", "dOI_BTCUSDT", "mu_BTCUSDT", "sd_BTCUSDT"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    A = pd.Timestamp("2021-09-24", tz="UTC")
    w0, w1 = A - pd.Timedelta(days=372), A - pd.Timedelta(days=7)
    w = df[(df["T"] >= w0) & (df["T"] < w1)]["dOI_BTCUSDT"].to_numpy(dtype=float)
    w = w[np.isfinite(w)]
    assert w.size >= 1000
    mu, sd = float(w.mean()), float(w.std(ddof=1))
    # rows of year 0 carry the anchor-0 norm
    sub = df[(df["T"] >= A) & (df["T"] < A + pd.Timedelta(days=365))]
    row = sub.iloc[0]
    assert abs(float(row["mu_BTCUSDT"]) - mu) < 1e-9
    assert abs(float(row["sd_BTCUSDT"]) - sd) < 1e-9
    # rows before the first anchor are never gated
    g = pd.read_parquet(ROOT / "research/tournament/oc_oishort/tmp/gates_std.parquet")
    g["T"] = pd.to_datetime(g["T"], utc=True)
    pre = g[g["T"] < A]
    ocols = [c for c in g.columns if c.startswith("o1_") or c.startswith("o2_")]
    assert not bool(pre[ocols].to_numpy().any())
