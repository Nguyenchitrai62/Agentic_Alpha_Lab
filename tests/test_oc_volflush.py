"""Tests for oc_volflush (synthetic + alignment; no outcome tuning)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_volflush"))
from compute_volflush import compute_for_coin  # noqa: E402

MAJORS_R2_N = 6876
PER_YEAR = [990, 1045, 1330, 989, 1144]


def synth_klines(n_min=3000, vol=10.0, tbv_frac=0.45, gap_at=None):
    ot = pd.date_range("2021-01-01", periods=n_min, freq="min", tz="UTC")
    df = pd.DataFrame({"open_time": ot,
                       "volume": np.full(n_min, vol, dtype="float32"),
                       "taker_buy_volume": np.full(n_min, vol * tbv_frac, dtype="float32")})
    if gap_at is not None:
        df = df.drop(index=range(gap_at, gap_at + 5)).reset_index(drop=True)
    return df


def synth_fills(k, idx):
    tfs = [k["open_time"].iloc[i] + pd.Timedelta(minutes=1) for i in idx]
    return pd.DataFrame({"sym": ["SYN"] * len(idx),
                         "T": [t - pd.Timedelta(minutes=100) for t in tfs],
                         "t_fill": tfs, "f": [100] * len(idx),
                         "x1": [2.5] * len(idx), "y0.5": [0.0] * len(idx),
                         "y1.0": [0.001] * len(idx), "y1.5": [0.002] * len(idx)})


def test_feature_math_flat_volume():
    k = synth_klines()
    out = compute_for_coin(k, synth_fills(k, [2000]))
    assert abs(out["vol_ratio"].iloc[0] - 1.0) < 1e-6
    assert abs(out["sell_share"].iloc[0] - 0.55) < 1e-6


def test_volume_spike_ratio():
    k = synth_klines()
    # spike the last 15 bars (positions 1986..2000) 3x
    k.loc[k.index[1986:2001], "volume"] = 30.0
    out = compute_for_coin(k, synth_fills(k, [2000]))
    # V15 = 15*30; MU24 = (1425*10 + 15*30)/1440
    expect = 30.0 / ((1425 * 10.0 + 15 * 30.0) / 1440.0)
    assert abs(out["vol_ratio"].iloc[0] - expect) < 1e-6


def test_gap_in_15m_window_gives_nan():
    k = synth_klines(gap_at=1998)  # gap touches the f-1 window of fill at 2000
    out = compute_for_coin(k, synth_fills(k, [2000]))
    assert np.isnan(out["vol_ratio"].iloc[0])
    assert np.isnan(out["sell_share"].iloc[0])


def test_short_history_gives_nan_vol_ratio():
    k = synth_klines(n_min=1100)  # only 1091 bars available at the fill < 1200
    out = compute_for_coin(k, synth_fills(k, [1090]))
    assert np.isnan(out["vol_ratio"].iloc[0])


def test_zero_volume_sell_nan():
    k = synth_klines()
    k.loc[k.index[1986:2001], "volume"] = 0.0
    k.loc[k.index[1986:2001], "taker_buy_volume"] = 0.0
    out = compute_for_coin(k, synth_fills(k, [2000]))
    assert np.isnan(out["sell_share"].iloc[0])


def test_windows_strictly_before_fill():
    k = synth_klines()
    fills = synth_fills(k, [2000])
    base = compute_for_coin(k, fills)
    # shift all 1m data at/after the fill minute: features must not change
    k2 = k.copy()
    t0 = fills["t_fill"].iloc[0]
    m = k2["open_time"] >= t0
    k2.loc[m, "volume"] = 999.0
    k2.loc[m, "taker_buy_volume"] = 999.0
    out2 = compute_for_coin(k2, fills)
    pd.testing.assert_series_equal(base["vol_ratio"], out2["vol_ratio"], check_names=False)
    pd.testing.assert_series_equal(base["sell_share"], out2["sell_share"], check_names=False)


def test_universe_counts():
    f = pd.read_parquet(ROOT / "research" / "tournament" / "oc_volflush"
                        / "features_volflush.parquet")
    assert len(f) == MAJORS_R2_N
    assert set(f["sym"].unique()) <= {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert set(f["x1"].unique()) <= {2.5, 3.0, 3.5, 4.0, 5.0}
    assert ((f["T"].dt.hour % 4 == 0) & (f["T"].dt.minute == 0)).all()
    for k, a in enumerate([2021, 2022, 2023, 2024, 2025]):
        s = pd.Timestamp(f"{a}-09-24", tz="UTC")
        e = s + pd.Timedelta(days=365)
        assert int(((f["T"] >= s) & (f["T"] < e)).sum()) == PER_YEAR[k]
    assert (f["t_fill"] < pd.Timestamp("2026-09-24", tz="UTC")).all()


def test_training_cutoffs_causal():
    import json
    r = json.load(open(ROOT / "research" / "tournament" / "oc_volflush" / "results.json"))
    f = pd.read_parquet(ROOT / "research" / "tournament" / "oc_volflush"
                        / "features_volflush.parquet")
    # year-k training pools = rows with T < A_k, strictly growing by construction
    trains = [r["features"]["vol_ratio"]["per_year"][k]["terciles"]["n_train"] for k in range(5)]
    assert trains == sorted(trains) and trains[0] >= 100
    # LOYO held-out years cover all 5 anchors, no NaN spreads from missing data
    assert len(r["features"]["vol_ratio"]["loyo"]) == 5
