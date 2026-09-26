"""Tests for v95+v96 blind audit (Part A). No leader v95/v96 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v95_v96_audit")
REP = AUD / "replication.json"
E96 = AUD / "equity_v96.csv"
E95 = AUD / "equity_v95.csv"
P95 = AUD / "predictions_v95.csv"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v95/v96 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert [a["anchor"] for a in d["anchors_v95"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    for a in d["anchors_v95"]:
        assert a["n_pred_rows"] == 10950
        assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
        assert a["train_rows"] > 0
    assert len(d["yearly_v95_normal"]) == 5 and len(d["yearly_v96_normal"]) == 5
    for y in d["yearly_v95_normal"] + d["yearly_v96_normal"]:
        assert y["bars"] == 2190
        assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert d["features_v95_count"] == len(d["features_v95"])
    assert d["features_v95_count"] > 26
    assert d["ctx_causality"]["passed"] is True


def test_cutoff_math_v95():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * (42 + 60))
        assert cutoff == a - pd.Timedelta(hours=408)


def test_equity_files_cover_five_years():
    for p in (E95, E96):
        df = pd.read_csv(p, parse_dates=["t"])
        assert len(df) == 10950
        assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
        assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_predictions_v95_cover_five_years():
    df = pd.read_csv(P95, parse_dates=["t"])
    assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert len(df) == 5 * 10950
    assert {"pred", "y"}.issubset(df.columns)
    assert {"xs_pct_ret42", "f7_z180"}.issubset(df.columns)


def test_v96_combined_weight_synthetic():
    w92 = pd.DataFrame({"A": [0.5, 0.0], "B": [0.5, 1.0]})
    s92 = pd.Series([1.0, 2.0])
    w94 = pd.DataFrame({"A": [0.2, -0.4], "B": [0.0, 0.4]})
    s94 = pd.Series([1.5, 0.5])
    wc = 0.5 * w92.mul(s92, axis=0) + 0.5 * w94.mul(s94, axis=0)
    assert np.allclose(wc.iloc[0].to_numpy(), [0.5 * 0.5 * 1.0 + 0.5 * 0.2 * 1.5, 0.5 * 0.5 * 1.0 + 0.0])
    assert (s92 <= 2.0).all() and (s94 <= 2.0).all()


def test_xs_pct_rank_synthetic():
    v = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    rk = v.rank(method="average")
    pct = (rk - 1) / (len(v) - 1)
    assert list(pct.round(4)) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_f7z_rolling_window_math():
    # 180d = 1080 4h bars, min 30d = 180 bars
    assert 180 * 6 == 1080
    assert 30 * 6 == 180
    s = pd.Series(np.arange(200, dtype=float))
    mu = s.rolling(1080, min_periods=180).mean()
    assert mu.iloc[:179].isna().all()
    assert mu.iloc[179:].notna().all()
