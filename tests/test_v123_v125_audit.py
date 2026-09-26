"""Tests for v123+v124+v125 blind audit (Part A). No leader v123/v124/v125 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v123_v125_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v123/v124/v125 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("v123", "v124", "v125", "meta")) <= set(d.keys())
    v123 = d["v123"]
    assert len(v123["anchors_v92"]) == 5 and len(v123["anchors_v94"]) == 5
    for a in v123["anchors_v92"]:
        assert a["n_pred_rows"] == 10950 and np.isfinite(a["ic"])
        assert a["train_rows"] > 0
    for a in v123["anchors_v94"]:
        assert a["n_pred_rows"] == 10950 and np.isfinite(a["ic_mean_vs_h42"])
    assert set(v123["primary"].keys()) == {"normal", "fee_stress", "execution_stress"}
    for sc in ("normal", "fee_stress", "execution_stress"):
        assert len(v123["primary"][sc]["yearly"]) == 5
        for y in v123["primary"][sc]["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] >= 0
    assert set(v123["blend"].keys()) == {"normal", "fee_stress", "execution_stress"}
    assert v123["n_oos"] == 10950
    for feat in ("r4_50", "r4_200", "rib4", "w50", "w50_slope", "ribw", "rib_agree"):
        assert feat in v123["features"], feat
    v124 = d["v124"]
    h = v124["hidden_year_1m_execution_strict"]
    assert np.isfinite(h["net_pct"]) and np.isfinite(h["max_drawdown_percent"])
    assert 0.0 <= h["maker_fill_rate"] <= 1.0
    assert h["orders_hidden_year"] > 0 and h["fills_hidden_year"] > 0
    v125 = d["v125"]
    assert set(v125["tranched"].keys()) == {"normal", "fee_stress", "execution_stress"}
    assert set(v125["reference_phase0"].keys()) == {"normal", "fee_stress", "execution_stress"}
    for sc in ("normal", "fee_stress", "execution_stress"):
        assert len(v125["tranched"][sc]["yearly"]) == 5
        assert len(v125["reference_phase0"][sc]["yearly"]) == 5


def test_v123_panel_counts_match_v114():
    import json as _j
    v114 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/replication.json").read_text())
    d = _rep()
    for b, l in zip(d["v123"]["anchors_v92"], v114["v114"]["anchors_v92"]):
        assert b["anchor"] == l["anchor"]
        assert b["train_rows"] == l["train_rows"], (b["anchor"], b["train_rows"], l["train_rows"])
    for b, l in zip(d["v123"]["anchors_v94"], v114["v114"]["anchors_v94"]):
        assert b["train_rows_h42"] == l["train_rows_h42"]


def test_v125_reference_phase0_equals_v115_primary():
    import json as _j
    v115 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v115_audit/replication.json").read_text())
    d = _rep()
    for sc in ("normal", "fee_stress", "execution_stress"):
        blind = d["v125"]["reference_phase0"][sc]["yearly"]
        ref = v115["primary_t15"][sc]["yearly"]
        for b, l in zip(blind, ref):
            assert abs(b["net_pct"] - l["net_pct"]) < 1e-9, (sc, b, l)
            assert abs(b["max_drawdown_percent"] - l["max_drawdown_percent"]) < 1e-9
            assert b["fills"] == l["fills"]
    assert abs(d["v125"]["reference_phase0"]["normal"]["full_path_dd"] - v115["primary_t15"]["normal"]["full_path_dd"]) < 1e-9


def test_predictions_causal_shape():
    for tag in ("predictions_v123_v92.csv", "predictions_v123_v94.csv"):
        p = pd.read_csv(AUD / tag, parse_dates=["t"])
        assert len(p) == 5 * 10950, (tag, len(p))
        assert set(p["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        assert p["pred"].notna().all()
        assert (p.groupby("sym").size() == 10950).all()
    h = pd.read_csv(AUD / "held_v124.csv", index_col=0, parse_dates=True)
    assert len(h) == 10950
    assert list(h.columns) == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
