"""Tests for v103+v104+v105 blind audit (Part A). No leader v103/v104/v105 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v103_v105_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v103/v104/v105 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["cutoff_rule_v103"].startswith("cutoff = anchor - 78*4h")
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert len(d["features_v92"]) == 26
    assert len(d["features_flow"]) == 10
    assert len(d["features_all"]) == 36
    for a in d["v103"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows_h6"] > a["train_rows_h18"] > 0
        for k in ("ic_vs_y6", "ic_vs_y18", "ic_vs_y42"):
            assert np.isfinite(a[k]) and -1.0 <= a[k] <= 1.0
    for key in ("yearly_LS_normal", "yearly_LO_normal", "yearly_blend_normal"):
        assert len(d["v103"][key]) == 5
        for y in d["v103"][key]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    for sc in ("normal", "fee_stress", "execution_stress"):
        assert len(d["v104"]["yearly"][sc]) == 5
    h = d["v104"]["hidden_1m_execution"]
    assert np.isfinite(h["net_pct"]) and np.isfinite(h["maker_rate"])
    assert 0.0 <= h["maker_rate"] <= 1.0
    assert h["total_orders"] > 0 and h["missing_1m"] >= 0
    assert len(d["v105a_noflow_LS"]["anchors"]) == 5
    assert len(d["v105b_7dflow_LO"]["anchors"]) == 5
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400


def test_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 78)
        assert cutoff == a - pd.Timedelta(hours=312)


def test_flow_features_synthetic():
    # tbr1 clip + tbr_k centering
    tbqv = pd.Series([0.0, 5.0, 15.0])
    qv = pd.Series([10.0, 10.0, 10.0]).clip(lower=1)
    tbr1 = (tbqv / qv).clip(lower=0, upper=1)
    assert list(tbr1.round(6)) == [0.0, 0.5, 1.0]
    tbr_1 = tbr1.rolling(1).mean() - 0.5
    assert list(tbr_1.round(6)) == [-0.5, 0.0, 0.5]
    # flow_k: signed volume share
    signed = (2 * tbr1 - 1) * qv
    flow_2 = signed.rolling(2).sum() / qv.rolling(2).sum()
    assert abs(flow_2.iloc[1] - ((-10.0 + 0.0) / 20.0)) < 1e-12
    # clv NaN on zero range
    high = pd.Series([10.0, 10.0]); low = pd.Series([10.0, 9.0])
    close = pd.Series([10.0, 9.5])
    rng = high - low
    clv = (close - low) / rng
    clv = clv.where(rng != 0, np.nan)
    assert np.isnan(clv.iloc[0]) and abs(clv.iloc[1] - 0.5) < 1e-12


def test_predictions_cover_five_years():
    for name in ("predictions_v103.csv", "predictions_v105a_noflow.csv", "predictions_v105b_7dflow.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(df) == 5 * 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_equity_files_cover_five_years():
    for name in ("equity_v103_LS.csv", "equity_v103_LO.csv", "equity_v103_blend.csv",
                 "equity_v104_normal.csv", "equity_v105a_noflow.csv", "equity_v105b_7dflow.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert len(df) == 10950
        assert df["net"].notna().all()
