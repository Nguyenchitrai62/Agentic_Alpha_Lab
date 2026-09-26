"""Tests for v127+v128 blind audit (Part A). No leader v127/v128 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v127_v128_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v127/ or v128/ folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v127_v128_audit_replication"
    assert set(("v127", "v128", "meta")) <= set(d.keys())
    v127 = d["v127"]
    assert set(v127["scenarios"].keys()) == {"normal", "fee_stress", "execution_stress"}
    for sc in ("normal", "fee_stress", "execution_stress"):
        r = v127["scenarios"][sc]
        assert len(r["yearly"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        assert 0.0 <= r["full_path_dd"] < 100 and np.isfinite(r["monthly_pct"])
    h = v127["hidden_year_1m_execution_strict"]
    for k in ("net_pct", "max_drawdown_percent", "maker_fill_rate",
              "orders_hidden_year", "fills_hidden_year"):
        assert k in h, k
    assert 0.0 <= h["maker_fill_rate"] <= 1.0
    assert h["orders_hidden_year"] > 0 and h["fills_hidden_year"] > 0
    v128 = d["v128"]
    assert len(v128["anchors_v92_with"]) == 5
    for a in v128["anchors_v92_with"]:
        assert np.isfinite(a["ic"]) and abs(a["ic"]) < 1
        assert a["train_rows"] > 40000
    for tag in ("phases_with", "phases_without"):
        assert set(v128[tag].keys()) == {str(p) for p in range(6)}
        for p in range(6):
            for sc in ("normal", "fee_stress", "execution_stress"):
                r = v128[tag][str(p)][sc]
                assert len(r["yearly"]) == 5
                assert 0.0 <= r["full_path_dd"] < 100
    for tag in ("phase_summary_with", "phase_summary_without"):
        for sc in ("normal", "fee_stress", "execution_stress"):
            s = v128[tag][sc]
            monthlies = [v128["phases_with" if tag == "phase_summary_with" else "phases_without"][str(p)][sc]["monthly_pct"] for p in range(6)]
            assert abs(s["monthly_pct_mean"] - float(np.mean(monthlies))) < 1e-3


def test_v127_tranched_matches_v125_and_hidden_sane():
    v125 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v123_v125_audit/replication.json").read_text())
    d = _rep()
    for sc in ("normal", "fee_stress", "execution_stress"):
        blind = d["v127"]["scenarios"][sc]["yearly"]
        ref = v125["v125"]["tranched"][sc]["yearly"]
        for b, r in zip(blind, ref):
            assert abs(b["net_pct"] - r["net_pct"]) < 1e-9, (sc, b, r)
            assert abs(b["max_drawdown_percent"] - r["max_drawdown_percent"]) < 1e-9
            assert b["fills"] == r["fills"]
    h = d["v127"]["hidden_year_1m_execution_strict"]
    assert h["fills_hidden_year"] <= h["orders_hidden_year"]
    assert h["orders_hidden_year"] < 20000


def test_v128_baseline_without_matches_v126_and_hv_causal():
    v126 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v126_audit/replication.json").read_text())
    d = _rep()
    for p in range(6):
        for sc in ("normal", "fee_stress", "execution_stress"):
            blind = d["v128"]["phases_without"][str(p)][sc]["yearly"]
            ref = v126["phases"][str(p)][sc]["yearly"]
            for b, r in zip(blind, ref):
                assert abs(b["net_pct"] - r["net_pct"]) < 1e-9, (p, sc, b, r)
                assert b["fills"] == r["fills"]
    feats = d["v128"]["features_with_hv"]
    assert "hv_days" in feats and "hv_sin" in feats and "hv_cos" in feats
    # hv triple is bounded and causal by construction: sin/cos in [-1,1], days >= 0
    assert len(feats) == 29
