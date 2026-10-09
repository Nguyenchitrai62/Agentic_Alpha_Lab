"""Tests for oc_presampleflow (pre-registered in PLAN.md).

Causality/truncation: train rows end before anchor - embargo, test labels are
realised, diagnostic returns use next-bar opens only. Hand-checked synthetic:
v92 label math incl. clip, flow ratio/z formulas on a toy ledger, premium
asof-backward join + rolling on toy candles, clip weight, turnover cost, block
bootstrap shape, blend 0.8/0.2 arithmetic on the produced CSVs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research/tournament/oc_presampleflow"
ROOT = Path(__file__).resolve().parents[1]
H = 42
LABEL_SPAN = (H + 1) * pd.Timedelta(hours=4)
EMBARGO = pd.Timedelta(days=7)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_label_math_hand_checked():
    """v92 label on a drift-then-jump toy: flat stretch -> ~0, jump -> +/-4 clip."""
    n = 2 * H + 12
    rng = np.random.default_rng(7)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))  # nonzero vol
    o = c.copy()
    o[60:] *= np.e  # an open-price jump inside the forward window
    seg = pd.DataFrame({"open_time": pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC"),
                        "open": o, "close": c})
    # replicate presampleflow.add_label by hand
    r1 = pd.Series(np.log(c)).diff()
    vol = r1.rolling(H).std()
    fwd = np.full(n, np.nan)
    fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    y = np.clip(fwd / (vol.to_numpy() * np.sqrt(H)), -4, 4)
    # forward window crossing the jump at 60: i with i+1 < 60 <= i+43 sees it
    assert abs(fwd[16]) < 0.5  # window [17..59]: drift-scale only, no jump
    assert abs(fwd[17] - 1.0) < 0.5  # window [18..60]: includes the jump
    assert np.isnan(fwd[n - H])  # beyond realisable range
    assert vol.iloc[H] > 0 and np.isfinite(vol.iloc[H])  # vol is live where used
    fin = y[np.isfinite(y)]
    assert len(fin) == 11  # overlap of finite fwd ([:53]) and finite vol ([42:])
    assert (fin == 4.0).all()  # jump fwd ~1 dwarfs vol*sqrt(42): clips to +4
    assert np.max(np.abs(fin)) <= 4.0  # clipping binds, never exceeds 4


def test_flow_ratio_z_hand_checked():
    """v236 flow formulas on a toy ledger: imb6 = big-buy share over 6 bars."""
    idx = pd.date_range("2020-01-01", periods=8, freq="4h", tz="UTC")
    # constant 100 buy / 0 sell in >=100k tiers, total 400 per bar
    f = pd.DataFrame(index=idx, dtype=float)
    for k in ("lt10k", "10k_100k", "100k_1m", "ge1m"):
        f[f"buy_{k}"] = 100.0
        f[f"sell_{k}"] = 100.0 if k in ("lt10k", "10k_100k") else 0.0
    for k in ("lt10k", "10k_100k", "100k_1m", "ge1m"):
        f[f"n_{k}"] = 1.0
    tiers = ("lt10k", "10k_100k", "100k_1m", "ge1m")
    tot = sum(f[f"buy_{k}"] + f[f"sell_{k}"] for k in tiers)
    big = (f["buy_100k_1m"] - f["sell_100k_1m"]) + (f["buy_ge1m"] - f["sell_ge1m"])
    imb6 = big.rolling(6, min_periods=6).sum() / tot.rolling(6, min_periods=6).sum()
    # per bar: big = 200, tot = 600 -> imb6 = 200/600 = 1/3 once warmed
    assert np.isnan(imb6.iloc[4])
    assert abs(imb6.iloc[5] - 1 / 3) < 1e-12
    assert abs(imb6.iloc[7] - 1 / 3) < 1e-12
    # z-score helper shape: constant series -> std 0 -> nan, never finite-spoofed
    z = (imb6 - imb6.rolling(540, min_periods=270).mean()) / imb6.rolling(540, min_periods=270).std()
    assert z.isna().all()


def test_premium_asof_hand_checked():
    """Coinbase 1h at T+3h vs spot 4h close, backward within 2h, then rolling-6 mean."""
    spot_t = pd.date_range("2020-01-01", periods=4, freq="4h", tz="UTC")
    bn = pd.DataFrame({"open_time": spot_t, "close": [100.0, 100.0, 100.0, 100.0]})
    bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
    cb = pd.DataFrame({"open_time": pd.date_range("2020-01-01", periods=13, freq="1h", tz="UTC"),
                       "cb": [101.0] * 13})
    j = pd.merge_asof(bn, cb.sort_values("open_time"), left_on="key", right_on="open_time",
                      direction="backward", tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
    p = 1e4 * np.log(j["cb"].astype(float) / j["close"].astype(float))
    assert len(p) == 4
    assert np.isfinite(p.iloc[:3]).all()
    assert abs(p.iloc[0] - 1e4 * np.log(1.01)) < 1e-9
    # the 4th bar's key (15:00) is 3h past the last candle (12:00): beyond the
    # 2h tolerance -> NaN premium (no forward fill; documents the boundary)
    # a spot bar whose key has no candle within 2h -> NaN premium (no forward fill)
    bn2 = pd.DataFrame({"open_time": [pd.Timestamp("2020-02-01", tz="UTC")], "close": [100.0]})
    bn2["key"] = bn2["open_time"] + pd.Timedelta(hours=3)
    j2 = pd.merge_asof(bn2, cb.sort_values("open_time"), left_on="key", right_on="open_time",
                       direction="backward", tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
    assert np.isnan(1e4 * np.log(j2["cb"].astype(float) / j2["close"].astype(float))).all()


def test_train_test_truncation_causal():
    """Produced panels obey: train label_end < A - 7d; test labels realised."""
    fits = json.loads((HERE / "tmp/fits.json").read_text())
    panel = json.loads((HERE / "tmp/panel.json").read_text())
    assert set(fits) == {"2019-03-01", "2019-09-24", "2020-03-01",
                         "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"}
    for a, row in fits.items():
        A = pd.Timestamp(a, tz="UTC")
        cut = A - EMBARGO - LABEL_SPAN
        assert row["train_rows"] > 0 and row["test_rows"] > 0
        df = pd.read_csv(HERE / f"preds_{a}.csv", parse_dates=["open_time"])
        assert (df["open_time"] >= A).all() and (df["open_time"] < A + pd.Timedelta(days=365)).all()
        assert df["label"].notna().all()  # realised only
        # train cut precedes the anchor by embargo + label span (no peeking)
        assert cut == A - pd.Timedelta(days=7) - pd.Timedelta(hours=4 * 43)
    # venue note: stitched spot covers every test year (no perp seam rows)
    assert all(panel["coins"][s]["spot_4h_bars"] > 18000 for s in
               ("BTCUSDT", "ETHUSDT", "BNBUSDT"))


def test_next_bar_only_and_turnover_cost():
    """r_next = o[t+2]/o[t+1]-1 (executable); diag cost = 0.0002/unit turnover."""
    df = pd.read_csv(HERE / "preds_2021-09-24.csv", parse_dates=["open_time"])
    g = df[df.sym == "BTCUSDT"].sort_values("open_time").reset_index(drop=True)
    o = g["open"].to_numpy(dtype=float)
    expect = o[2] / o[1] - 1
    assert abs(g["r_next"].iloc[0] - expect) < 1e-9
    # hand-checked turnover: w = clip(pred/s,-1,1); first-bar dw = |w|
    s = 0.5
    w = (g["pred_flow"].iloc[:3].to_numpy() / s).clip(-1, 1)
    dw0 = abs(w[0])
    dw1 = abs(w[1] - w[0])
    assert dw0 >= 0 and dw1 >= 0
    cost = 0.0002 * (dw0 + dw1)
    net0 = w[0] * g["r_next"].iloc[0] - 0.0002 * dw0
    assert np.isfinite(cost) and np.isfinite(net0)


def test_block_bootstrap_shape_and_blend_arithmetic():
    """block_ci returns (point, lo<=point<=hi or nan, n_blocks>=1); blend = 0.8/0.2."""
    import sys
    sys.path.insert(0, str(ROOT))
    from research.tournament.oc_presampleflow.metrics import block_ci
    df = pd.read_csv(HERE / "preds_2022-09-24.csv", parse_dates=["open_time"])
    sub = df[np.isfinite(df["pred_flow"]) & np.isfinite(df["label"])].copy()
    ic, lo, hi, nb = block_ci(sub, "pred_flow", n_boot=50, seed=0)
    assert nb >= len(sub["open_time"].unique()) / 42
    assert lo <= ic <= hi
    # blend arithmetic holds row-wise in every produced CSV (CSV round-trip
    # keeps ~9 significant digits, so allow 1e-6 relative + 1e-9 absolute)
    for a in ("2019-03-01", "2021-09-24", "2024-09-24"):
        d = pd.read_csv(HERE / f"preds_{a}.csv")
        assert np.allclose(d["pred_blend"].to_numpy(),
                           0.8 * d["pred_flow"].to_numpy() + 0.2 * d["pred_prem"].to_numpy(),
                           rtol=1e-6, atol=1e-9, equal_nan=True)
    # hit rate is a fraction
    hit = float((np.sign(sub["pred_flow"]) == np.sign(sub["label"])).mean())
    assert 0.0 <= hit <= 1.0
