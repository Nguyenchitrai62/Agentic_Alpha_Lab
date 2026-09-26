"""Tests for v126 blind audit (Part A). No leader v126 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v126_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v126/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(("phases", "phase_summary", "yearly_normal_nets", "meta")) <= set(d.keys())
    assert set(d["phases"].keys()) == {str(p) for p in range(6)}
    for p in range(6):
        ph = d["phases"][str(p)]
        assert set(ph.keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = ph[sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] >= 0
            assert 0.0 <= r["full_path_dd"] < 100
            assert np.isfinite(r["monthly_pct"])
    for sc in ("normal", "fee_stress", "execution_stress"):
        s = d["phase_summary"][sc]
        monthlies = [d["phases"][str(p)][sc]["monthly_pct"] for p in range(6)]
        assert abs(s["monthly_pct_mean"] - float(np.mean(monthlies))) < 1e-3
        assert s["monthly_pct_min"] == round(float(np.min(monthlies)), 3)
        assert s["monthly_pct_max"] == round(float(np.max(monthlies)), 3)
    assert set(d["yearly_normal_nets"].keys()) == {
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"}
    for a, v in d["yearly_normal_nets"].items():
        assert len(v["per_phase_net_pct"]) == 6
        assert abs(v["mean"] - float(np.mean(v["per_phase_net_pct"]))) < 0.011


def test_phase0_equals_v115_primary():
    import json as _j
    v115 = _j.loads(Path("research/parallel/rounds/parallel-20260906-r2/v115_audit/replication.json").read_text())
    d = _rep()
    for sc in ("normal", "fee_stress", "execution_stress"):
        blind = d["phases"]["0"][sc]["yearly"]
        ref = v115["primary_t15"][sc]["yearly"]
        for b, l in zip(blind, ref):
            assert abs(b["net_pct"] - l["net_pct"]) < 1e-9, (sc, b, l)
            assert abs(b["max_drawdown_percent"] - l["max_drawdown_percent"]) < 1e-9
            assert b["fills"] == l["fills"]
        assert abs(d["phases"]["0"][sc]["monthly_pct"] - v115["primary_t15"][sc]["monthly_pct"]) < 1e-9
        assert abs(d["phases"]["0"][sc]["full_path_dd"] - v115["primary_t15"][sc]["full_path_dd"]) < 1e-9


def test_phases_differ_and_cover_union():
    d = _rep()
    # phases must not be all identical (subsampling changes timing)
    monthlies = [d["phases"][str(p)]["normal"]["monthly_pct"] for p in range(6)]
    assert len(set(monthlies)) > 1
    # union bars implied: each phase yearly months == 12.0 and fills > 0
    for p in range(6):
        for y in d["phases"][str(p)]["normal"]["yearly"]:
            assert y["months"] == 12.0
            assert y["fills"] > 0
