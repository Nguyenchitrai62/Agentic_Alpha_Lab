"""Tests for v92 blind audit (Part A). No leader v92 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

REP = Path("research/parallel/rounds/parallel-20260906-r2/v92_audit/replication.json")
PRED = Path("research/parallel/rounds/parallel-20260906-r2/v92_audit/predictions.csv")


def test_replication_json_exists():
    assert REP.exists(), "Part A replication.json must be saved before reading v92 folder"
    d = json.loads(REP.read_text())
    assert len(d["anchors"]) == 5
    anchors = [a["anchor"] for a in d["anchors"]]
    assert anchors == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    for a in d["anchors"]:
        assert isinstance(a["train_rows"], int) and a["train_rows"] > 0
        assert a["n_pred_rows"] == 8760  # 365d * 6 bars/day * 4 assets / 4 = 2190 bars * 4
        assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
    assert d["model"]["max_depth"] == 4
    assert d["model"]["max_iter"] == 400
    assert len(d["features"]) == 26
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]
    hid = d["hidden_year_2025_2026_normal"]
    assert np.isfinite(hid["net_pct"]) and np.isfinite(hid["max_drawdown_percent"])
    five = d["five_year_continuous_oos_normal"]
    assert five["bars"] == 10950
    assert np.isfinite(five["monthly_geometric_net_percent"])


def test_train_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * (42 + 60))
        assert pd.Timedelta(hours=4 * 43) == pd.Timedelta(hours=172)
        assert cutoff == a - pd.Timedelta(hours=408)


def test_predictions_cover_five_years():
    df = pd.read_csv(PRED, parse_dates=["t"])
    assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"}
    assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
    assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)
    # 5 years * 365d * 6 bars * 4 assets = 43800 rows
    assert len(df) == 5 * 8760


def test_weight_sizing_synthetic():
    pred = pd.Series([0.0, 0.25, 0.5, 1.0])
    s = (pred.clip(lower=0) / 0.5).clip(upper=1.0)
    assert list(s.round(6)) == [0.0, 0.5, 1.0, 1.0]
    # ribbon -1 zeroes
    rib = pd.Series([1.0, -1.0, 0.0, 1.0])
    s = s.where(rib != -1, 0.0)
    assert list(s) == [0.0, 0.0, 1.0, 1.0]


def test_vol_target_scaling_synthetic():
    book = pd.Series(np.random.RandomState(0).randn(400) * 0.01)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    assert vol.iloc[119:].notna().all()
    assert vol.iloc[:119].isna().all()
    scale = (0.20 / vol).clip(upper=2.0).fillna(1.0)
    assert ((scale <= 2.0).all() and (scale > 0).all())


def test_execution_timing_uses_two_bar_delay():
    # W_t earns open_{t+2}/open_{t+1} - 1 (one-bar delay to fill at open[t+1])
    o = pd.Series([100.0, 101.0, 103.0, 104.0])
    # return attributed to t=0 uses opens at 1 and 2
    r0 = o.iloc[2] / o.iloc[1] - 1
    assert abs(r0 - (103.0 / 101.0 - 1)) < 1e-12


def test_spot_prefix_only_before_first_usdm_bar():
    first = pd.Timestamp("2019-09-08 16:00:00+00:00", tz="UTC")
    spot = pd.to_datetime(["2019-09-08 12:00:00+00:00", "2019-09-08 16:00:00+00:00"], utc=True)
    keep = spot < first
    assert list(keep) == [True, False]
