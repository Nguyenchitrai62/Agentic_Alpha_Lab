"""Tests for v107+v108 blind audit (Part A). No leader v107/v108 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v107_v108_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v107/v108 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["cutoff_rule"].startswith("cutoff = anchor - 78*4h")
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert len(d["features_v103"]) == 36
    assert d["features_ih"] == ["ih_last", "ih_jump", "ih_rv", "ih_ac", "ih_tbr", "ih_up"]
    assert len(d["features_v107"]) == 42
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400
    for a in d["v103_base"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows_h6"] > a["train_rows_h18"] > 0
    for a in d["v107"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows_h6"] > a["train_rows_h18"] > 0
        for k in ("ic_vs_y6", "ic_vs_y18"):
            assert np.isfinite(a[k]) and -1.0 <= a[k] <= 1.0
    for sc in ("normal", "fee_stress", "execution_stress"):
        assert len(d["v107"]["yearly_LS"][sc]) == 5
        assert len(d["v107"]["yearly_blend_v96"][sc]) == 5
        for y in d["v107"]["yearly_LS"][sc] + d["v107"]["yearly_blend_v96"][sc]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    for k in ("k=1", "k=3", "k=6"):
        assert k in d["v108"]
        for sc in ("normal", "fee_stress", "execution_stress"):
            assert len(d["v108"][k][sc]) == 5
            for y in d["v108"][k][sc]:
                assert y["bars"] == 2190
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])


def test_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 78)
        assert cutoff == a - pd.Timedelta(hours=312)


def test_ih_features_synthetic():
    # tbr clip to [0,1]
    tbqv = pd.Series([0.0, 5.0, 15.0])
    qv = pd.Series([10.0, 10.0, 10.0]).clip(lower=1)
    tbr = (tbqv / qv).clip(lower=0, upper=1)
    assert list(tbr.round(6)) == [0.0, 0.5, 1.0]
    # ih_last = r1 / sd168
    r1 = pd.Series([0.01, -0.02, 0.03])
    sd = pd.Series([0.02, 0.02, 0.02])
    assert list((r1 / sd).round(6)) == [0.5, -1.0, 1.5]
    # ih_up: NaN where r1 NaN, then rolling mean - 0.5
    r1n = pd.Series([np.nan, 0.01, -0.01, 0.02])
    up = pd.Series(np.where(r1n.isna(), np.nan, (r1n > 0).astype(float)))
    assert np.isnan(up.iloc[0]) and list(up.iloc[1:]) == [1.0, 0.0, 1.0]
    ih_up2 = up.rolling(2).mean() - 0.5
    assert np.isnan(ih_up2.iloc[0]) and abs(ih_up2.iloc[2] - 0.0) < 1e-12
    # ih_jump: rolling-4 max |r1| / sd
    j = r1.abs().rolling(2).max() / sd
    assert abs(j.iloc[1] - (0.02 / 0.02)) < 1e-12


def test_hour_mapping_convention():
    # 4h bar at T takes the 1h bar at T+3h  <=>  t_4h = t_1h - 3h
    t4 = pd.Timestamp("2021-09-24 00:00", tz="UTC")
    t1 = pd.Timestamp("2021-09-24 03:00", tz="UTC")
    assert t1 == t4 + pd.Timedelta(hours=3)
    assert t4 == t1 - pd.Timedelta(hours=3)


def test_predictions_cover_five_years():
    for name, need_ih in (("predictions_v103.csv", False), ("predictions_v107.csv", True)):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(df) == 5 * 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)
        if need_ih:
            for c in ("ih_last", "ih_jump", "ih_rv", "ih_ac", "ih_tbr", "ih_up"):
                assert c in df.columns


def test_equity_files_cover_five_years():
    names = ["equity_v107_LS_normal.csv", "equity_v107_LS_fee_stress.csv",
             "equity_v107_LS_execution_stress.csv", "equity_v107_blend_normal.csv",
             "equity_v108_k1_normal.csv", "equity_v108_k3_normal.csv", "equity_v108_k6_normal.csv"]
    for name in names:
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert len(df) == 10950
        assert df["net"].notna().all()
