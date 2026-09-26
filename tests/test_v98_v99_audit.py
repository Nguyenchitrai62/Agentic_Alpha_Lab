"""Tests for v98+v99 blind audit (Part A). No leader v98/v99 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v98_v99_audit")
REP = AUD / "replication.json"
E98H2 = AUD / "equity_v98_H2.csv"
E98H1 = AUD / "equity_v98_H1.csv"
E99 = AUD / "equity_v99.csv"
E99X = AUD / "equity_v99_hidden_exec.csv"
P98H2 = AUD / "predictions_v98_H2.csv"
P98H1 = AUD / "predictions_v98_H1.csv"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v98/v99 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    for key in ("anchors_v98_H2", "anchors_v98_H1"):
        anchors = d[key]
        assert [a["anchor"] for a in anchors] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        for a in anchors:
            assert a["n_pred_rows"] == 10950
            assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
            assert a["train_rows"] > 0
            assert a["w_max"] <= 1.0 + 1e-9 and a["w_min"] >= 0.0
    for key in ("yearly_v98_H2_normal", "yearly_v98_H1_normal", "yearly_v99_normal"):
        assert len(d[key]) == 5
        for y in d[key]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert "0.5**(age_years / H)" in d["recency_weight"]
    hx = d["hidden_v99_1m_execution"]
    assert 0.0 <= hx["maker_rate"] <= 1.0
    assert hx["total_orders"] > 0 and hx["bars"] == 2190


def test_cutoff_math_v98():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * (42 + 60))
        assert cutoff == a - pd.Timedelta(hours=408)


def test_recency_weight_synthetic():
    age = pd.Series([0.0, 1.0, 2.0, 4.0])
    w2 = 0.5 ** (age / 2.0)
    w1 = 0.5 ** (age / 1.0)
    assert np.allclose(w2.to_numpy(), [1.0, 0.5 ** 0.5, 0.5, 0.25])
    assert np.allclose(w1.to_numpy(), [1.0, 0.5, 0.25, 0.0625])
    assert (w1 <= w2).all()  # shorter half-life decays faster


def test_equity_files_cover_five_years():
    for p in (E98H2, E98H1, E99):
        df = pd.read_csv(p, parse_dates=["t"])
        assert len(df) == 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_predictions_v98_cover_five_years():
    for p in (P98H2, P98H1):
        df = pd.read_csv(p, parse_dates=["t"])
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(df) == 5 * 10950
        assert {"pred", "y"}.issubset(df.columns)


def test_hidden_exec_file():
    df = pd.read_csv(E99X, parse_dates=["t"])
    assert len(df) == 2190
    assert {"net_exec", "extra_cost"}.issubset(df.columns)
    assert (df["extra_cost"] >= -1e-12).all()  # execution extras are costs only


def test_v99_combined_weight_synthetic():
    w92 = pd.DataFrame({"A": [0.5, 0.0], "B": [0.5, 1.0]})
    s92 = pd.Series([1.0, 2.0])
    w94 = pd.DataFrame({"A": [0.2, -0.4], "B": [0.0, 0.4]})
    s94 = pd.Series([1.5, 0.5])
    books = 0.5 * w92.mul(s92, axis=0) + 0.5 * w94.mul(s94, axis=0)
    assert np.allclose(books.iloc[0].to_numpy(), [0.5 * 0.5 * 1.0 + 0.5 * 0.2 * 1.5, 0.5 * 0.5 * 1.0 + 0.0])
    s = pd.Series([0.5, 3.0])
    s = s.clip(upper=2.0)
    assert list(s) == [0.5, 2.0]


def test_limit_fill_synthetic():
    # strict trade-through: touch-without-crossing does not fill
    limit = 100.0
    assert bool(np.any(np.array([99.9]) < limit)) is True  # buy fills on strict through
    assert bool(np.any(np.array([100.0]) < limit)) is False  # touch alone does not fill
    assert bool(np.any(np.array([100.1]) > limit)) is True  # sell fills on strict through
    assert bool(np.any(np.array([100.0]) > limit)) is False
