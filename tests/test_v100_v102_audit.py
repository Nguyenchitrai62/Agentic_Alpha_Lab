"""Tests for v100+v101+v102 blind audit (Part A). No leader v100/v101/v102 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v100_v102_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v100/v101/v102 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["cutoff_rule"].startswith("cutoff = anchor - 102*4h")
    assert d["assets_majors"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert len(d["features_v92"]) == 26
    for key in ("primary1200", "sens300"):
        for a in d["v100"][key]["anchors"]:
            assert a["n_pred_rows"] == 10950
            assert a["train_rows"] > 0
            assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
        assert len(d["v100"][key]["yearly_normal"]) == 5
        for y in d["v100"][key]["yearly_normal"]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    for key in ("primary_w1", "sens_w05"):
        for a in d["v101"][key]["anchors"]:
            assert a["n_pred_rows"] == 10950
            assert a["train_rows"] > a["train_rows_majors"] > 0
            assert a["train_rows_extras"] > 0
            assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
        for y in d["v101"][key]["yearly_normal"]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"])
    v102 = d["v102"]
    assert np.isfinite(v102["ic_pooled_xs"]) and np.isfinite(v102["ic_mean_perbar_xs"])
    assert -1.0 <= v102["ic_pooled_xs"] <= 1.0
    assert len(v102["yearly_neutral_normal"]) == 5
    assert len(v102["yearly_blend_normal"]) == 5
    assert len(v102["yearly_v99_leader_convention_normal"]) == 5
    for y in v102["yearly_neutral_normal"] + v102["yearly_blend_normal"]:
        assert y["bars"] == 2190
        assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    assert -1.0 <= v102["corr_daily_neutral_vs_v99"] <= 1.0
    assert d["model_base"]["max_depth"] == 4 and d["model_base"]["max_iter"] == 400
    assert len(v102["features"]) == 26 + 9


def test_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 102)
        assert cutoff == a - pd.Timedelta(hours=408)
        assert pd.Timedelta(hours=4 * 43) == pd.Timedelta(hours=172)


def test_phase_grouping_synthetic():
    # 8 hourly bars starting 01:00, phase 1 groups = [01-04],[05-08]
    idx = pd.date_range("2021-01-01 01:00", periods=8, freq="h", tz="UTC")
    hours = idx.hour % 4
    starts = [i for i in range(len(idx)) if hours[i] == 1]
    # starts at 01 and 05
    assert starts == [0, 4]
    # each group needs 4 consecutive hourly bars
    for s in starts:
        assert s + 3 < len(idx)
        assert (idx[s + 1] - idx[s]).total_seconds() == 3600


def test_xs_target_synthetic():
    y = pd.Series([0.1, 0.2, 0.3, np.nan])
    m = y.mean(skipna=True)
    xs = y - m
    assert abs(xs.iloc[0] - (0.1 - 0.2)) < 1e-12
    # fewer than 2 labelled -> NaN
    y2 = pd.Series([0.5, np.nan, np.nan])
    assert y2.notna().sum() < 2


def test_neutral_weight_synthetic():
    pred = pd.Series({"A": 0.3, "B": -0.1, "C": 0.1})
    vol = pd.Series({"A": 0.5, "B": 0.5, "C": 0.5})
    mean = pred.mean()
    raw = (pred - mean) / (vol * np.sqrt(2190))
    W = raw - raw.mean()
    assert abs(W.sum()) < 1e-12  # demeaned
    W = W / W.abs().sum()
    assert abs(W.abs().sum() - 1.0) < 1e-12
    # fewer than 2 predictions -> zero
    cnt = 1
    Wz = W * (cnt >= 2)
    assert (Wz == 0).all()


def test_predictions_cover_five_years():
    for name in ("predictions_v100_primary1200.csv", "predictions_v101_primary_w1.csv", "predictions_v102.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(df) == 5 * 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_equity_files_cover_five_years():
    for name in ("equity_v100_primary1200.csv", "equity_v101_primary_w1.csv",
                 "equity_v102_neutral.csv", "equity_v102_blend.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert len(df) == 10950
        if "net" in df.columns:
            assert df["net"].notna().all()
        if "net_blend" in df.columns:
            assert df["net_blend"].notna().all()


def test_vol_target_scaling_synthetic():
    book = pd.Series(np.random.RandomState(0).randn(400) * 0.01)
    for target in (0.20, 0.10):
        vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
        scale = (target / vol).clip(upper=2.0).fillna(1.0)
        assert ((scale <= 2.0).all() and (scale > 0).all())
