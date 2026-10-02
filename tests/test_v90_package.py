"""v90 worker tests: causality, hand-checked synthetics, capacity band, smoke.

Scope: ONLY the v90 Kaggle package (bundle + standalone train script).
No forward returns for dates >= 2025-09-24 are computed or inspected here:
label tests assert the hidden-year guard structurally (NaN labels), and the
smoke run covers anchor 2021-09-24 only.

v90 revision 2026-09-25: per-asset availability masking (45 input channels),
BTC-only window gating, open-based labels (y7=log(open[t+43]/open[t+1])/vol).
"""
import torch  # must precede pandas on this Windows host

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
V90 = REPO / "research" / "parallel" / "rounds" / "parallel-20260906-r2" / "v90"
sys.path.insert(0, str(V90 / "kaggle"))

import train_v90 as t

H = 4 * 3600_000_000_000  # 4h in ns


def _synthetic_bundle(n: int = 1300) -> dict:
    """Deterministic ramp market for all 5 assets (hand-checkable)."""
    rng = np.random.default_rng(7)
    grid = (1_600_000_000_000_000_000 + np.arange(n) * H).astype(np.int64)
    b: dict = {"close_time_4h_ns": grid, "assets": np.array(t.ASSETS)}
    for m, a in enumerate(t.ASSETS):
        base = 100.0 + m * 10.0
        close = base + 0.05 * np.arange(n) + rng.normal(0, 0.2, n).cumsum() * 0.01
        close = np.maximum(close, 1.0)
        b[f"{a}.open"] = close - 0.01
        b[f"{a}.high"] = close + 0.05
        b[f"{a}.low"] = close - 0.05
        b[f"{a}.close"] = close
        b[f"{a}.volume"] = 1000.0 + 10.0 * np.arange(n)
        # daily bars: every 6th grid bar closes a day
        dct = grid[5::6]
        b[f"{a}.daily_close_time_ns"] = dct
        b[f"{a}.daily_close"] = close[5::6]
        # funding every 2nd grid bar
        b[f"{a}.funding_time_ns"] = grid[::2]
        b[f"{a}.funding_rate"] = np.full(len(grid[::2]), 0.0001)
    return b


def test_synthetic_hand_checked_features():
    b = _synthetic_bundle()
    X, avail, btc_ok, info = t.build_features(b)
    assert X.shape == (1300, 40)
    assert avail.shape == (1300, 5)
    assert btc_ok.shape == (1300,)
    c = b["BTCUSDT.close"]
    # lr1 at t=10
    assert X[10, 0] == pytest.approx(float(np.log(c[10] / c[9])), rel=1e-5)
    # lr6 at t=10
    assert X[10, 1] == pytest.approx(float(np.log(c[10] / c[4])), rel=1e-5)
    # lr42 at t=100
    assert X[100, 2] == pytest.approx(float(np.log(c[100] / c[58])), rel=1e-5)
    # range at t=10
    assert X[10, 3] == pytest.approx((b["BTCUSDT.high"][10] - b["BTCUSDT.low"][10]) / c[10], rel=1e-6)
    # funding 7d mean: grid[::2] fundings; at grid t=100, fundings <= t are
    # indices 0..50 -> last 21 all 0.0001
    assert X[100, 5] == pytest.approx(0.0001, rel=1e-6)
    # SMA50 distance at t=399: daily closes as of last daily <= grid[399]
    dc = b["BTCUSDT.daily_close"]
    sma50 = dc[-50:].mean()
    sma200 = dc[-200:].mean()
    assert X[1299, 6] == pytest.approx((c[1299] - sma50) / sma50, rel=1e-6)
    assert X[1299, 7] == pytest.approx((c[1299] - sma200) / sma200, rel=1e-6)
    # volume z uses trailing window ending at t (causal, finite here)
    assert np.isfinite(X[1299, 4])
    # early rows are not feature-complete
    assert not btc_ok[0] and btc_ok[1299]
    # availability: all-complete synthetic market -> 1 wherever BTC complete
    assert (avail[1299] == 1.0).all()
    assert (avail[0] == 0.0).all()
    assert (info["feat_ok_all"][1299])
    assert (not info["feat_ok_all"][0])


def test_synthetic_hand_checked_open_labels():
    """Open-based labels: y7=log(open[t+43]/open[t+1])/vol, y1=log(open[t+7]/open[t+1])/vol."""
    b = _synthetic_bundle(1300)
    cutoff = 100_000_000_000_000_000_000  # far future: form all labels
    Y7, Y1, end = t.build_labels(b, cutoff)
    assert Y7.shape == (1300, 5)
    o = b["BTCUSDT.open"]
    c = b["BTCUSDT.close"]
    lr1 = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    vol = pd.Series(lr1).rolling(42, min_periods=42).std(ddof=0).to_numpy()
    tt = 500
    assert Y7[tt, 0] == pytest.approx(float(np.log(o[tt + 43] / o[tt + 1]) / vol[tt]), rel=1e-5)
    assert Y1[tt, 0] == pytest.approx(float(np.log(o[tt + 7] / o[tt + 1]) / vol[tt]), rel=1e-5)
    # label END time is grid[t+43]
    assert end[tt] == b["close_time_4h_ns"][tt + 43]
    # tail rows with no forward window stay NaN
    assert not np.isfinite(Y7[1299, 0])


def test_synthetic_btc_only_gating_and_masking():
    """Non-BTC assets missing late: BTC windows still valid, avail masks them."""
    b = _synthetic_bundle(1600)
    # Wipe SOL late (simulate missing/unavailable asset): NaN OHLCV for last 300 bars
    for col in ("open", "high", "low", "close", "volume"):
        arr = b["SOLUSDT." + col].copy()
        arr[1300:] = np.nan
        b["SOLUSDT." + col] = arr
    X, avail, btc_ok, info = t.build_features(b)
    # BTC still complete late; SOL wiped late so its trailing features are NaN
    assert btc_ok[1599]
    assert avail[1599, 0] == 1.0 and avail[1599, 2] == 0.0
    assert not info["feat_ok_all"][1599]
    # early rows are incomplete for BTC itself (SMA200 warmup)
    assert avail[500, 0] == 0.0 and not btc_ok[500]
    # zero-fill + 45ch assembly (mirrors train_v90.main): finite on BTC windows
    mu = np.nanmean(X[1200:1290], axis=0).astype(np.float32)
    sd = np.nanstd(X[1200:1290], axis=0).astype(np.float32)
    sd = np.where(np.isfinite(sd) & (sd > 1e-8), sd, 1.0).astype(np.float32)
    mu = np.where(np.isfinite(mu), mu, 0.0).astype(np.float32)
    Xn_feat = ((X - mu) / sd).astype(np.float32)
    Xn_feat[~np.isfinite(Xn_feat)] = 0.0
    Xn = np.concatenate([Xn_feat, avail.astype(np.float32)], axis=1)
    assert Xn.shape == (1600, 45)
    win_btc = pd.Series(btc_ok.astype(np.float32)).rolling(t.WIN, min_periods=t.WIN).min().to_numpy() == 1.0
    assert win_btc[1599]
    assert np.isfinite(Xn[1599]).all()
    # availability channel flags the masked asset
    assert Xn[1599, 40 + 0] == 1.0 and Xn[1599, 40 + 2] == 0.0
    # labels: SOL late NaN, BTC finite -> BTC-only label_ok keeps the row
    cutoff = 100_000_000_000_000_000_000
    Y7, Y1, _ = t.build_labels(b, cutoff)
    assert np.isfinite(Y7[500, 0]) and np.isfinite(Y7[500, 2])
    assert np.isfinite(Y7[1260, 0]) and not np.isfinite(Y7[1260, 2])
    # Huber loss masks NaN labels
    p = torch.zeros(2, 5)
    y = torch.tensor(np.stack([Y7[500], Y7[501]]).astype(np.float32))
    assert torch.isfinite(t.huber(p, y))


def test_synthetic_causality_append_future():
    """Appending future bars must not change earlier feature rows."""
    b = _synthetic_bundle(1300)
    X_full, avail_full, _, _ = t.build_features(b)
    trunc = {k: (v[:1000] if isinstance(v, np.ndarray) and len(v) == 1300 else v) for k, v in b.items()}
    # keep daily/funding consistent lengths is unnecessary: builder uses
    # searchsorted, truncation of those arrays only removes future availability
    for a in t.ASSETS:
        trunc[f"{a}.daily_close_time_ns"] = b[f"{a}.daily_close_time_ns"][
            b[f"{a}.daily_close_time_ns"] < b["close_time_4h_ns"][1000]]
        trunc[f"{a}.daily_close"] = b[f"{a}.daily_close"][
            : len(trunc[f"{a}.daily_close_time_ns"])]
        trunc[f"{a}.funding_time_ns"] = b[f"{a}.funding_time_ns"][
            b[f"{a}.funding_time_ns"] < b["close_time_4h_ns"][1000]]
        trunc[f"{a}.funding_rate"] = b[f"{a}.funding_rate"][
            : len(trunc[f"{a}.funding_time_ns"])]
    X_tr, avail_tr, _, _ = t.build_features(trunc)
    np.testing.assert_allclose(X_tr[:1000], X_full[:1000], rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(avail_tr[:1000], avail_full[:1000], rtol=0, atol=0)


def test_real_bars_causality_truncation():
    """Real data: features on full grid vs grid minus last 200 bars agree."""
    b = dict(np.load(V90 / "majors_4h_bundle.npz", allow_pickle=False))
    X_full, avail_full, _, _ = t.build_features(b)
    n = len(b["close_time_4h_ns"])
    trunc = {}
    for k, v in b.items():
        if k == "assets":
            trunc[k] = v
        elif k == "close_time_4h_ns":
            trunc[k] = v[: n - 200]
        elif k.endswith(".daily_close_time_ns") or k.endswith(".funding_time_ns"):
            trunc[k] = v[v < b["close_time_4h_ns"][n - 200]]
        elif k.endswith(".daily_close") or k.endswith(".funding_rate"):
            a = k.split(".")[0]
            tk = f"{a}.daily_close_time_ns" if "daily" in k else f"{a}.funding_time_ns"
            trunc[k] = v[: (trunc[tk].shape[0])]
        else:
            trunc[k] = v[: n - 200]
    X_tr, avail_tr, _, _ = t.build_features(trunc)
    np.testing.assert_allclose(X_tr, X_full[: n - 200], rtol=1e-5, atol=1e-7)
    np.testing.assert_allclose(avail_tr, avail_full[: n - 200], rtol=0, atol=0)


def test_hidden_year_labels_never_formed():
    b = dict(np.load(V90 / "majors_4h_bundle.npz", allow_pickle=False))
    grid = b["close_time_4h_ns"].astype("int64")
    cutoff = pd.Timestamp(t.HIDDEN_CUTOFF, tz="UTC").value
    Y7, Y1, end = t.build_labels(b, cutoff)
    formed = np.isfinite(Y7[:, 0])  # BTC y7 gates training
    assert formed.any()  # protocol still has training labels
    assert (end[formed] < cutoff).all()
    assert not np.isfinite(Y7[grid >= cutoff]).any()
    assert not np.isfinite(Y1[grid >= cutoff]).any()


def test_param_count_in_band():
    m = t.PooledSequenceModel()
    n = t.count_params(m)
    assert t.N_CHAN == 45
    assert m.in_proj.in_features == 45
    assert 2_000_000 <= n <= 10_000_000, n


def test_bundle_manifest_hash():
    man = json.loads((V90 / "data_manifest.json").read_text())
    path = V90 / man["bundle"]
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == man["sha256"]
    assert man["grid"]["last_close"].startswith("2026-09-24")
    assert set(man["grid"]["assets"]) == set(t.ASSETS)


def test_smoke_run_cpu_subset(tmp_path):
    # Isolate each test run and preserve existing research checkpoints.
    out = tmp_path / "v90_smoke"
    cmd = [sys.executable, str(V90 / "kaggle" / "train_v90.py"),
           "--bundle", str(V90 / "majors_4h_bundle.npz"),
           "--manifest", str(V90 / "data_manifest.json"),
           "--out", str(out), "--smoke", "--device", "cpu"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-3000:]
    summ = json.loads((out / "run_summary.json").read_text())
    assert summ["smoke"] is True
    assert 2_000_000 <= summ["params"] <= 10_000_000
    assert list(summ["anchors"]) == [t.ANCHORS[0]]
    pred = pd.read_parquet(out / "predictions" / f"pred_{t.ANCHORS[0]}.parquet")
    assert len(pred) == 2190
    assert np.isfinite(pred.filter(like="_y7_").to_numpy()).all()
    assert (out / "checkpoints" / f"ckpt_{t.ANCHORS[0]}_seed0.pt").exists()
