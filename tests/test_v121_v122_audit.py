"""Tests for v121+v122 blind audit (Part A). No leader v121/v122 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v121_v122_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v121/v122/"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("v121", "v122", "meta")) <= set(d.keys())
    v121 = d["v121"]
    assert set(("ic", "book_bagged_LS_own_scale", "portfolio_v115_with_bag_025_025_05_t15_ungoverned")) <= set(v121.keys())
    assert v121["bag"]["members"] == 10 and abs(v121["bag"]["sample_frac"] - 0.7) < 1e-12
    assert v121["horizons"] == [6, 18]
    assert len(v121["features"]) == 36
    for sc in ("normal", "fee_stress", "execution_stress"):
        for sec in ("book_bagged_LS_own_scale", "portfolio_v115_with_bag_025_025_05_t15_ungoverned"):
            r = v121[sec][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0
            assert 0.0 <= r["full_path_dd"] < 100
    v122 = d["v122"]
    assert v122["target"] == "y168"
    assert len(v122["features"]) == 26
    assert set(("ic", "book_y168_LS_own_scale", "portfolio_02_02_04_02_t15_ungoverned")) <= set(v122.keys())
    for sc in ("normal", "fee_stress", "execution_stress"):
        for sec in ("book_y168_LS_own_scale", "portfolio_02_02_04_02_t15_ungoverned"):
            r = v122[sec][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert 0.0 <= r["full_path_dd"] < 100
    m = d["meta"]
    assert m["target"] == 0.15 and m["governed"] is False
    assert m["union_bars_v121"] == 10950 and m["union_bars_v122"] == 10950
    assert m["n_live_bars_v121"] == 10944 and m["n_live_bars_v122"] == 10944


def test_ic_finite_and_train_rows():
    d = _rep()
    for a, rec in d["v121"]["ic"].items():
        assert np.isfinite(rec["ic_y6"]) and np.isfinite(rec["ic_y18"])
        assert rec["train_rows"]["6"] > 30000 and rec["train_rows"]["18"] > 30000
        assert rec["train_rows"]["sample_days_h6"] == int(0.7 * rec["train_rows"]["n_days_h6"])
    for a, rec in d["v122"]["ic"].items():
        assert np.isfinite(rec["ic_y168"])
        assert rec["train_rows"] > 40000


def test_predictions_causal_shape():
    for fn, ycol in (("predictions_v121_bag.csv", "y6"), ("predictions_v122_y168.csv", "y168")):
        p = AUD / fn
        assert p.exists()
        df = pd.read_csv(p, parse_dates=["t"])
        assert len(df) == 5 * 2190 * 5 or len(df) == 54750, len(df)
        assert set(("t", "sym", "open", "pred", "vol42", "rib", ycol)) <= set(df.columns)
        assert df["pred"].notna().all()
