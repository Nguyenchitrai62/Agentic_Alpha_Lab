"""Tests for v118+v119 blind audit (Part A). No leader v118/v119 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v118_v119_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v118/ or v119/"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("v118_bands", "v119", "meta")) <= set(d.keys())
    bands = d["v118_bands"]
    assert set(bands.keys()) == {"primary_band002", "secondary_band005", "reference_band000"}
    for bkey, res in bands.items():
        assert set(res.keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = res[sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0
            assert 0.0 <= r["full_path_dd"] < 100
    v19 = d["v119"]
    assert len(v19["anchors"]) == 5
    for a in v19["anchors"]:
        assert a["train_rows"] > 0 and a["n_pred_rows"] == 10950
        assert np.isfinite(a["test_ic"])
        assert set(("max_depth", "min_samples_leaf", "val_spearman")) <= set(a["best"].keys())
        assert len(a["grid_scores"]) == 6
    assert set(v19["yearly"].keys()) == {
        "v92_lo_new_normal", "v92_lo_new_fee_stress", "v92_lo_new_execution_stress",
        "v96_blend_new94_normal", "v96_blend_new94_fee_stress", "v96_blend_new94_execution_stress",
    }
    assert d["meta"]["a1"]["union_bars"] == 10950
    assert d["meta"]["a1"]["n_live_bars"] == 10944
    assert v19["n_oos"] == 10950


def test_band_reference_equals_v115_primary():
    import json as _j
    v115 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v115_audit/replication.json").read_text())
    d = _rep()
    for sc in ("normal", "fee_stress", "execution_stress"):
        blind = d["v118_bands"]["reference_band000"][sc]["yearly"]
        leader = v115["primary_t15"][sc]["yearly"]
        for b, l in zip(blind, leader):
            assert abs(b["net_pct"] - l["net_pct"]) < 1e-9, (sc, b, l)
            assert abs(b["max_drawdown_percent"] - l["max_drawdown_percent"]) < 1e-9
            assert b["fills"] == l["fills"]
    assert abs(d["v118_bands"]["reference_band000"]["normal"]["full_path_dd"]
               - v115["primary_t15"]["normal"]["full_path_dd"]) < 1e-9


def test_band_monotone_fills_and_cost():
    d = _rep()
    # wider band => fewer or equal fills (same targets, turnover path nested per-asset threshold)
    for sc in ("normal", "fee_stress", "execution_stress"):
        f0 = sum(y["fills"] for y in d["v118_bands"]["reference_band000"][sc]["yearly"])
        f2 = sum(y["fills"] for y in d["v118_bands"]["primary_band002"][sc]["yearly"])
        f5 = sum(y["fills"] for y in d["v118_bands"]["secondary_band005"][sc]["yearly"])
        assert f0 >= f2 >= f5, (sc, f0, f2, f5)
        assert f0 > 0 and f5 > 0


def test_a2_panel_counts_match_v114():
    import json as _j
    v114 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/replication.json").read_text())
    d = _rep()
    for b, l in zip(d["v119"]["anchors"], v114["v114"]["anchors_v92"]):
        assert b["anchor"] == l["anchor"]
        assert b["train_rows"] == l["train_rows"], (b["anchor"], b["train_rows"], l["train_rows"])
    # 2021 best config is the v114 baseline so test IC must match exactly
    assert d["v119"]["anchors"][0]["best"] == {"max_depth": 4, "min_samples_leaf": 300, "val_spearman": 0.1221}
    assert abs(d["v119"]["anchors"][0]["test_ic"] - 0.0863) < 1e-9


def test_a2_predictions_causal_shape():
    p = pd.read_csv(AUD / "predictions_v119.csv", parse_dates=["t"])
    assert len(p) == 5 * 10950
    assert set(p["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert p["pred"].notna().all()
    assert (p.groupby("sym").size() == 10950).all()
