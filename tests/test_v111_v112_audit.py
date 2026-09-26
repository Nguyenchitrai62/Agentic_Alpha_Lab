"""Tests for v111+v112 blind audit (Part A). No leader v111/v112 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v111_v112_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v111/v112 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["cutoff_rule_v103"].startswith("cutoff = anchor - 78*4h")
    assert d["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    assert len(d["features_v92"]) == 26
    assert len(d["features_flow"]) == 10
    assert len(d["features_all"]) == 36
    assert d["features_cb"] == ["cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"]
    assert len(d["features_v111_primary"]) == 41
    assert len(d["features_v111_secondary"]) == 31
    assert d["model_reg"]["max_depth"] == 4 and d["model_reg"]["max_iter"] == 400
    assert d["model_clf"]["max_depth"] == 4 and d["model_clf"]["max_iter"] == 400
    for a in d["v111_primary"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows_h6"] > a["train_rows_h18"] > 0
        for k in ("ic_vs_y6", "ic_vs_y18", "ic_vs_y42"):
            assert np.isfinite(a[k]) and -1.0 <= a[k] <= 1.0
    for a in d["v111_secondary"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows"] > 0
        assert np.isfinite(a["ic_vs_y42"])
    for a in d["v112_primary"]["anchors"]:
        assert a["n_pred_rows"] == 10950
        assert a["train_rows_h6"] > a["train_rows_h18"] > 0
        for k in ("ic_vs_y6", "ic_vs_y18", "ic_vs_y42"):
            assert np.isfinite(a[k]) and -1.0 <= a[k] <= 1.0
    for sc in ("normal", "fee_stress", "execution_stress"):
        assert len(d["v111_primary"]["yearly"][sc]) == 5
        assert len(d["v111_secondary"]["yearly"][sc]) == 5
        assert len(d["v112_primary"]["yearly"][sc]) == 5
        assert len(d["v112_secondary"]["yearly"][sc]) == 5
        for y in d["v111_primary"]["yearly"][sc]:
            assert y["bars"] == 2190
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])


def test_cutoff_embargo_math():
    for anchor in ["2021-09-24", "2025-09-24"]:
        a = pd.Timestamp(anchor, tz="UTC")
        assert a - pd.Timedelta(hours=4 * 78) == a - pd.Timedelta(hours=312)
        assert a - pd.Timedelta(hours=4 * 102) == a - pd.Timedelta(hours=408)


def test_cb_features_synthetic():
    # cbp = 1e4*log(cb/bin); p6/p42/m540 windows + min_periods
    bin_close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    cb_close = pd.Series([100.0, 101.0, 102.0, 101.0, 100.0, 99.0, 100.0])
    cbp = 1e4 * np.log(cb_close / bin_close)
    assert abs(cbp.iloc[0]) < 1e-12 and cbp.iloc[2] > cbp.iloc[1] > 0
    p6 = cbp.rolling(6, min_periods=4).mean()
    assert np.isnan(p6.iloc[2]) is False or True  # min 4 -> first 3 NaN
    assert np.isnan(p6.iloc[2]) and np.isfinite(p6.iloc[3])
    p42 = cbp.rolling(42, min_periods=30).mean()
    assert np.isnan(p42.iloc[6])  # only 7 obs < 30
    dev = p6 - cbp.rolling(540, min_periods=270).mean()
    assert np.isnan(dev.iloc[6])  # m540 needs 270
    # asof backward tolerance: key=T+3h matches 1h open at T+3h, misses beyond 2h
    left = pd.DataFrame({"key": pd.to_datetime(["2021-01-01 03:00"], utc=True)})
    right = pd.DataFrame({"key": pd.to_datetime(["2021-01-01 03:00", "2021-01-01 02:00"], utc=True),
                          "v": [7.0, 6.0]})
    m = pd.merge_asof(left.sort_values("key"), right.sort_values("key"), on="key",
                      direction="backward", tolerance=pd.Timedelta(hours=2))
    assert m["v"].iloc[0] == 7.0
    m2 = pd.merge_asof(pd.DataFrame({"key": pd.to_datetime(["2021-01-01 06:00"], utc=True)}),
                       pd.DataFrame({"key": pd.to_datetime(["2021-01-01 03:00"], utc=True), "v": [7.0]}),
                       on="key", direction="backward", tolerance=pd.Timedelta(hours=2))
    assert np.isnan(m2["v"].iloc[0])


def test_clf_pred_range():
    df = pd.read_csv(AUD / "predictions_v112_primary.csv", parse_dates=["t"])
    assert ((df["pred"] >= -1.0 - 1e-9) & (df["pred"] <= 1.0 + 1e-9)).all()
    assert ((df["pup_h6"] >= 0.0) & (df["pup_h6"] <= 1.0)).all()
    assert ((df["pup_h18"] >= 0.0) & (df["pup_h18"] <= 1.0)).all()


def test_predictions_cover_five_years():
    for name in ("predictions_v111_primary.csv", "predictions_v111_secondary.csv",
                 "predictions_v112_primary.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert len(df) == 5 * 10950
        for c in ("cb_btc_z", "cb_eth_z") if "v111" in name else ():
            assert c in df.columns


def test_equity_files_cover_five_years():
    for name in ("equity_v111_primary.csv", "equity_v111_secondary.csv",
                 "equity_v112_primary.csv", "equity_v112_blend.csv"):
        df = pd.read_csv(AUD / name, parse_dates=["t"])
        assert len(df) == 10950
        assert df["net"].notna().all()
