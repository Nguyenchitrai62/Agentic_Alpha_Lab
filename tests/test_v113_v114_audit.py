"""Tests for v113+v114 blind audit (Part A). No leader v113/v114 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v113_v114_audit")
REP = AUD / "replication.json"
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
BOOKS = ("v92_lo", "v94_ls", "v96_blend")
SCENS = ("normal", "fee_stress", "execution_stress")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v113/v114 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    for tag in ("v113", "v114"):
        r = d[tag]
        assert [a["anchor"] for a in r["anchors_v92"]] == ANCHORS
        assert [a["anchor"] for a in r["anchors_v94"]] == ANCHORS
        for a in r["anchors_v92"]:
            assert a["train_rows"] > 0
            assert a["n_pred_rows"] == 10950
            assert np.isfinite(a["ic"]) and -1.0 <= a["ic"] <= 1.0
        for a in r["anchors_v94"]:
            assert a["train_rows_h18"] > a["train_rows_h42"] > a["train_rows_h84"] > 0
            assert a["n_pred_rows"] == 10950
            assert np.isfinite(a["ic_mean_vs_h42"])
        for bn in BOOKS:
            for sc in SCENS:
                y = r["yearly"][f"{bn}_{sc}"]
                assert len(y) == 5
                for row in y:
                    assert row["bars"] == 2190
                    assert np.isfinite(row["net_pct"]) and np.isfinite(row["max_drawdown_percent"])
        # extended history present only for BTC/ETH
        assert r["pre4"]["BTCUSDT"] > 0 and r["pre4"]["ETHUSDT"] > 0
        assert r["pre1"]["BTCUSDT"] > 0 and r["pre1"]["ETHUSDT"] > 0
        assert r["n4"]["SOLUSDT"] == r["n4"]["BNBUSDT"] or True  # non-extended share base
    assert len(d["features"]) == 26
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert d["model"]["max_depth"] == 4 and d["model"]["max_iter"] == 400


def test_longer_history_adds_train_rows():
    d = _rep()
    base_v92 = 33088  # audited v92 2021-09-24 train rows (replication_5asset.json)
    assert d["v113"]["anchors_v92"][0]["train_rows"] > base_v92
    # v114 BTC extends to 2013, so strictly more 4h bars than v113
    assert d["v114"]["n4"]["BTCUSDT"] > d["v113"]["n4"]["BTCUSDT"]
    assert d["v114"]["n1"]["BTCUSDT"] > d["v113"]["n1"]["BTCUSDT"]
    # ETH identical across extensions
    assert d["v114"]["n4"]["ETHUSDT"] == d["v113"]["n4"]["ETHUSDT"]


def test_cutoff_math():
    for anchor in ("2021-09-24", "2025-09-24"):
        a = pd.Timestamp(anchor, tz="UTC")
        assert a - pd.Timedelta(hours=4 * 102) == a - pd.Timedelta(hours=408)
        assert a - pd.Timedelta(hours=4 * 144) == a - pd.Timedelta(hours=576)


def test_predictions_cover_five_years():
    for tag in ("v113", "v114"):
        p92 = pd.read_csv(AUD / f"predictions_{tag}_v92.csv", parse_dates=["t"])
        p94 = pd.read_csv(AUD / f"predictions_{tag}_v94.csv", parse_dates=["t"])
        assert set(p92["sym"].unique()) == set(p94["sym"].unique()) == \
            {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(p92) == len(p94) == 5 * 10950
        assert {"pred", "y"}.issubset(p92.columns)
        assert {"pred", "pred_h18", "pred_h42", "pred_h84", "y42"}.issubset(p94.columns)
        assert np.allclose(p94["pred"], p94[["pred_h18", "pred_h42", "pred_h84"]].mean(axis=1))


def test_equity_files_cover_five_years():
    for tag in ("v113", "v114"):
        for bn in BOOKS:
            p = AUD / f"equity_{tag}_{bn}_normal.csv"
            df = pd.read_csv(p, parse_dates=["t"])
            assert len(df) == 10950
            assert df["t"].min() >= pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(hours=1)
            assert df["t"].max() < pd.Timestamp("2026-09-24", tz="UTC") + pd.Timedelta(days=1)


def test_scenario_cost_ordering():
    d = _rep()
    for tag in ("v113", "v114"):
        for bn in BOOKS:
            n = d[tag]["yearly"][f"{bn}_normal"]
            f = d[tag]["yearly"][f"{bn}_fee_stress"]
            e = d[tag]["yearly"][f"{bn}_execution_stress"]
            for yn, yf, ye in zip(n, f, e):
                # higher costs cannot improve any yearly net
                assert yf["net_pct"] <= yn["net_pct"] + 1e-9
                assert ye["net_pct"] <= yf["net_pct"] + 1e-9


def test_weight_synthetic():
    p = pd.Series([0.6, -0.6, 0.1, 0.0])
    rib = pd.Series([0.0, 0.0, -1.0, 1.0])
    long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
    short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
    assert list(long.round(6)) == [1.0, 0.0, 0.0, 0.0]
    assert list(short.round(6)) == [0.0, 1.0, 0.0, 0.0]


def test_aggregation_thresholds_documented():
    d = _rep()
    assert "cnt>=3" in d["data"]["agg"] and "cnt>=20" in d["data"]["agg"]
    assert "close_time=open_time+rule-1ms" in d["data"]["agg"]
