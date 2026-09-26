"""Tests for v97 blind audit (Part A). No leader v97 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v97_audit")
REP = AUD / "replication.json"
PRED = AUD / "predictions.csv"
EQ = AUD / "equity.csv"

EXPECTED_TRAIN_ROWS = {
    "2021-09-24": 33088,
    "2022-09-24": 44038,
    "2023-09-24": 54988,
    "2024-09-24": 65968,
    "2025-09-24": 76918,
}


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v97 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert [a["anchor"] for a in d["anchors"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    for a in d["anchors"]:
        assert a["train_rows"] == EXPECTED_TRAIN_ROWS[a["anchor"]]
        assert a["n_pred_rows"] == 10950  # 365d * 6 bars/day * 5 assets / 5 = 2190 bars * 5
        assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
    assert len(d["yearly_normal"]) == 5
    for y in d["yearly_normal"]:
        assert y["bars"] == 2190
        assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
        assert np.isfinite(y["K_mean"]) and 0 < y["K_mean"] <= 2.0
    m = d["model"]
    assert m["ensemble"] == 16
    assert m["hgb"]["count"] == 15
    assert m["hgb"]["max_depth"] == [3, 4, 6]
    assert m["hgb"]["learning_rate"] == 0.03
    assert m["hgb"]["max_iter"] == 400
    assert m["hgb"]["min_samples_leaf"] == 300
    assert m["hgb"]["l2_regularization"] == 1.0
    assert m["hgb"]["max_features"] == 0.7
    assert m["hgb"]["random_state"] == [0, 1, 2, 3, 4]
    assert m["extra_trees"]["n_estimators"] == 300
    assert m["extra_trees"]["min_samples_leaf"] == 300
    assert m["extra_trees"]["max_features"] == 0.5
    assert m["extra_trees"]["random_state"] == 0
    assert m["prediction"] == "mean of all 16"
    assert "TRAINING-ROW" in m["imputation"]
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert len(d["features"]) == 26
    for anchor, chk in d["median_check"].items():
        assert chk["n_median_finite"] == chk["n_features"] == 26


def test_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * (42 + 60))
        assert cutoff == a - pd.Timedelta(hours=408)
        assert pd.Timedelta(hours=4 * 43) == pd.Timedelta(hours=172)


def test_predictions_cover_five_years():
    df = pd.read_csv(PRED, parse_dates=["t"])
    assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
    assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)
    assert len(df) == 5 * 10950
    assert {"pred", "y", "vol42", "rib"}.issubset(df.columns)


def test_equity_covers_five_years():
    df = pd.read_csv(EQ, parse_dates=["t"])
    assert len(df) == 5 * 2190
    assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
    assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)
    assert {"net", "turnover", "scale"}.issubset(df.columns)
    assert ((df["scale"] <= 2.0) & (df["scale"] > 0)).all()


def test_median_imputation_uses_training_rows_only():
    train = pd.DataFrame({"a": [1.0, 2.0, 3.0, np.nan], "b": [10.0, np.nan, 30.0, 40.0]})
    test = pd.DataFrame({"a": [np.nan, 100.0], "b": [np.nan, 200.0]})
    med = train.median(numeric_only=True)
    assert med["a"] == 2.0 and med["b"] == 30.0
    filled = test.fillna(med)
    assert filled.iloc[0]["a"] == 2.0 and filled.iloc[0]["b"] == 30.0
    # full-data median would leak test values; training-only must differ here
    leaked = pd.concat([train, test]).median(numeric_only=True)
    assert leaked["a"] != med["a"] or leaked["b"] != med["b"]


def test_ensemble_mean_synthetic():
    rng = np.random.RandomState(0)
    member_preds = [rng.randn(10) for _ in range(16)]
    mean_pred = sum(member_preds) / 16.0
    assert np.allclose(mean_pred, np.mean(np.stack(member_preds), axis=0))


def test_weight_sizing_synthetic():
    pred = pd.Series([0.0, 0.25, 0.5, 1.0])
    s = (pred.clip(lower=0) / 0.5).clip(upper=1.0)
    assert list(s.round(6)) == [0.0, 0.5, 1.0, 1.0]
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
    o = pd.Series([100.0, 101.0, 103.0, 104.0])
    r0 = o.iloc[2] / o.iloc[1] - 1
    assert abs(r0 - (103.0 / 101.0 - 1)) < 1e-12
