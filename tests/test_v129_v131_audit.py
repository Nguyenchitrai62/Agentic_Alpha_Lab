"""Tests for v129+v130+v131 blind audit (Part A). No leader v129/v130/v131 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v129/v130/v131 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("v129", "v130", "v131", "meta")) <= set(d.keys())
    for key in ("v129", "v130", "v131"):
        assert "phase_summary" in d[key] or f"phase_summary_with_pvol" in d[key] or "phases" in d[key]
    v129 = d["v129"]
    assert set(v129["phases_with_pvol"].keys()) == {str(p) for p in range(6)}
    assert set(v129["phases_with_vol42"].keys()) == {str(p) for p in range(6)}
    for p in range(6):
        for sc in ("normal", "fee_stress", "execution_stress"):
            assert np.isfinite(v129["phases_with_pvol"][str(p)][sc]["monthly_pct"])
            assert np.isfinite(v129["phases_with_vol42"][str(p)][sc]["monthly_pct"])
    v130 = d["v130"]
    assert set(v130["phases"].keys()) == {str(p) for p in range(6)}
    assert len(v130["anchors"]) == 5
    v131 = d["v131"]
    assert set(v131["phases"].keys()) == {str(p) for p in range(6)}
    assert set(v131["phases_without_k"].keys()) == {str(p) for p in range(6)}


def test_v129_spearmans_and_replacement():
    d = _rep()["v129"]
    assert len(d["anchors_v114"]) == 5 and len(d["anchors_v103"]) == 5
    for a in d["anchors_v114"] + d["anchors_v103"]:
        assert a["train_rows"] > 0
        assert a["n_pred_rows"] > 0
    assert d["n_replaced"]["v114_lo"] > 0
    assert d["n_replaced"]["v114_ls"] > 0
    assert d["n_replaced"]["v103"] > 0
    for sc in ("normal", "fee_stress", "execution_stress"):
        s = d["phase_summary_with_pvol"][sc]
        monthlies = [d["phases_with_pvol"][str(p)][sc]["monthly_pct"] for p in range(6)]
        assert abs(s["monthly_pct_mean"] - float(np.mean(monthlies))) < 1e-3


def test_vol42_baseline_equals_v126():
    import json as _j
    v126 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v126_audit/replication.json").read_text())
    d = _rep()["v129"]
    for p in range(6):
        for sc in ("normal", "fee_stress", "execution_stress"):
            b = d["phases_with_vol42"][str(p)][sc]
            r = v126["phases"][str(p)][sc]
            assert abs(b["monthly_pct"] - r["monthly_pct"]) < 1e-9, (p, sc)
            assert abs(b["full_path_dd"] - r["full_path_dd"]) < 1e-9


def test_v131_k_stats_and_phases_differ():
    d = _rep()["v131"]
    for k in ("lo", "ls94", "ls103"):
        st = d["k_stats"][k]
        assert 0.5 <= st["mean"] <= 2.0
    monthlies = [d["phases"][str(p)]["normal"]["monthly_pct"] for p in range(6)]
    assert len(set(monthlies)) > 1
    for p in range(6):
        for y in d["phases"][str(p)]["normal"]["yearly"]:
            assert y["fills"] > 0
