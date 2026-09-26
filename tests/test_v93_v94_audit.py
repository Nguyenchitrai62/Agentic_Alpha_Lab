"""Tests for v93+v94 blind audit (Part A). No leader v93/v94 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v93_v94_audit")
REP = AUD / "replication.json"
P94 = AUD / "predictions_v94.csv"
E94 = AUD / "equity_v94.csv"
E93 = AUD / "equity_v93.csv"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v93/v94 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert [a["anchor"] for a in d["anchors_v94"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    for a in d["anchors_v94"]:
        # per-horizon realised-label filtering => h18 > h42 > h84 rows
        assert a["train_rows_h18"] > a["train_rows_h42"] > a["train_rows_h84"] > 0
        assert a["n_pred_rows"] == 10950  # 2190 bars * 5 assets
        assert np.isfinite(a["ic_mean_vs_h42"]) and -1.0 <= a["ic_mean_vs_h42"] <= 1.0
    assert len(d["yearly_v94_normal"]) == 5 and len(d["yearly_v93_normal"]) == 5
    for y in d["yearly_v94_normal"] + d["yearly_v93_normal"]:
        assert y["bars"] == 2190
        assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400
    assert len(d["features"]) == 26
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def test_cutoff_math_v94():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * (84 + 60))
        assert cutoff == a - pd.Timedelta(hours=576)


def test_predictions_v94_cover_five_years():
    df = pd.read_csv(P94, parse_dates=["t"])
    assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert len(df) == 5 * 10950
    assert {"pred", "pred_h18", "pred_h42", "pred_h84", "y42"}.issubset(df.columns)
    assert np.allclose(df["pred"], df[["pred_h18", "pred_h42", "pred_h84"]].mean(axis=1))


def test_equity_files_cover_five_years():
    for p in (E94, E93):
        df = pd.read_csv(p, parse_dates=["t"])
        assert len(df) == 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_long_short_weight_synthetic():
    p = pd.Series([0.6, -0.6, 0.1, 0.0])
    rib = pd.Series([0.0, 0.0, -1.0, 1.0])
    long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
    short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
    assert list(long.round(6)) == [1.0, 0.0, 0.0, 0.0]
    assert list(short.round(6)) == [0.0, 1.0, 0.0, 0.0]
    raw = pd.Series([0.5, -0.25, 0.0, 0.0, 0.1])
    w = raw / raw.abs().sum() * min(1, (raw != 0).sum() / 5)
    assert abs(w.sum() - (0.5 - 0.25 + 0.1) / 0.85 * 0.6) < 1e-12


def test_v93_vol_target_uses_015_cap2():
    book = pd.Series(np.random.RandomState(1).randn(400) * 0.01)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    s = (0.15 / vol).clip(upper=2.0).fillna(1.0)
    assert ((s <= 2.0).all() and (s > 0).all())
    assert vol.iloc[:119].isna().all() and vol.iloc[119:].notna().all()


def test_carry_file_alignment():
    c = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")
    assert list(c.columns) == ["carry"]
    assert len(c) == 10950
    assert float(c["carry"].isna().mean()) == 0.0
