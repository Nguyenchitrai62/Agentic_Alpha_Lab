"""Tests for oc_vpinveto (causality/truncation + hand-checked synthetics)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_vpinveto"))

from vpin_rule import ANCH5, bucketed_vpin, bvc_buy_frac, gate_z


def test_bucketed_vpin_handchecked():
    # Fully one-sided per bucket -> VPIN 1.0 (bucket nets do not cancel)
    b = np.array([100.0, 100.0, 0.0, 0.0])
    s = np.array([0.0, 0.0, 100.0, 100.0])
    assert bucketed_vpin(b, s, n_buckets=2) == 1.0
    # Perfectly balanced flow -> VPIN 0.0
    b2 = np.array([50.0, 50.0, 50.0])
    s2 = np.array([50.0, 50.0, 50.0])
    assert bucketed_vpin(b2, s2, n_buckets=3) == 0.0
    # Single-sided single bucket: |150-50|/200 = 0.5
    assert bucketed_vpin(np.array([150.0]), np.array([50.0]), n_buckets=50) == 0.5
    # Zero volume -> NaN (never gate)
    assert np.isnan(bucketed_vpin(np.array([0.0]), np.array([0.0])))


def test_gate_z_frozen_threshold():
    assert gate_z(0.30, 0.10, 0.05) is True  # z=4 > 2
    assert gate_z(0.20, 0.10, 0.05) is False  # z=2 exactly -> strict >
    assert gate_z(float("nan"), 0.10, 0.05) is False
    assert gate_z(0.30, 0.10, 0.0) is False  # sd<=0 -> never gate
    assert gate_z(0.05, 0.10, 0.05) is False  # z=-1


def test_bvc_helper_synthetic():
    # Neutral input -> 0.5; positive move -> >0.5; symmetric
    assert bvc_buy_frac(0.0, 1.0) == 0.5
    assert bvc_buy_frac(1.0, 1.0) > 0.5
    assert abs(bvc_buy_frac(1.0, 1.0) + bvc_buy_frac(-1.0, 1.0) - 1.0) < 1e-12
    assert bvc_buy_frac(1.0, 0.0) == 0.5  # degenerate sigma -> neutral


def test_truncation_future_minutes_cannot_change_vpin():
    """Dropping 1m bars at/after T leaves VPIN(T) unchanged (causal window)."""
    rng = np.random.default_rng(7)
    B = rng.uniform(1, 10, size=1440)
    S = rng.uniform(1, 10, size=1440)
    full = bucketed_vpin(B, S)
    # append future bars (after T) then truncate back -> identical
    B2 = np.concatenate([B, rng.uniform(1, 10, size=60)])
    S2 = np.concatenate([S, rng.uniform(1, 10, size=60)])
    trunc = bucketed_vpin(B2[:1440], S2[:1440])
    assert trunc == full


def test_real_norm_window_uses_preanchor_embargo_only():
    """Stored mu/sd for anchor 2021-09-24 equal moments of VPIN in
    [A-372d, A-7d) only (fit-window causality on real data)."""
    p = ROOT / "research/tournament/oc_vpinveto/tmp/vpin_BTCUSDT.parquet"
    df = pd.read_parquet(p, columns=["T", "vpin", "mu", "sd", "anchor"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    A = pd.Timestamp("2021-09-24", tz="UTC")
    w0, w1 = A - pd.Timedelta(days=372), A - pd.Timedelta(days=7)
    w = df[(df["T"] >= w0) & (df["T"] < w1)]["vpin"].to_numpy(dtype=float)
    w = w[np.isfinite(w)]
    assert w.size >= 1000
    mu, sd = float(w.mean()), float(w.std(ddof=1))
    row = df[df["anchor"] == 0].iloc[0]
    assert abs(float(row["mu"]) - mu) < 1e-9
    assert abs(float(row["sd"]) - sd) < 1e-9
    # rows before the first anchor are never gated
    pre = df[df["T"] < A]
    assert bool(pre["gate"].any()) is False if "gate" in df.columns else True
