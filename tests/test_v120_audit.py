"""Tests for v120 blind audit (Part A). No leader v120 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v120_audit")
REP = AUD / "replication.json"
TARGET_KEYS = ("t010", "t012", "t015", "t018", "t020", "t022", "t025")
TARGET_VALS = {"t010": 0.10, "t012": 0.12, "t015": 0.15, "t018": 0.18, "t020": 0.20, "t022": 0.22, "t025": 0.25}


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v120/"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert set(TARGET_KEYS) <= set(d.keys()), set(d.keys())
    for key in TARGET_KEYS:
        assert set(d[key].keys()) == {"normal", "fee_stress", "execution_stress"}
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = d[key][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert np.isfinite(r["monthly_pct"]) and np.isfinite(r["worst_year_dd"])
                assert y["fills"] >= 0
            assert 0.0 <= r["full_path_dd"] < 100
    assert d["meta"]["band"] == 0.05
    assert d["meta"]["governed"] is False
    assert d["meta"]["targets"] == [0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25]
    assert d["meta"]["union_bars"] == 10950
    assert d["meta"]["n_live_bars"] == 10944


def test_t015_equals_v118_band005():
    v118 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v118/v118_result.json").read_text())
    d = _rep()
    for sc in ("normal", "fee_stress", "execution_stress"):
        blind = d["t015"][sc]["yearly"]
        leader = v118["secondary_band005"][sc]["yearly"]
        for b, l in zip(blind, leader):
            assert abs(b["net_pct"] - l["net_pct"]) < 1e-9, (sc, b, l)
            assert abs(b["max_drawdown_percent"] - l["max_drawdown_percent"]) < 1e-9, (sc, b, l)
            assert b["fills"] == l["fills"], (sc, b, l)
        for k in ("monthly_pct", "worst_year_dd", "full_path_dd"):
            assert abs(d["t015"][sc][k] - v118["secondary_band005"][sc][k]) < 1e-9, (sc, k)


def test_target_monotone_scale():
    d = _rep()
    # Higher vol target => weakly higher gross exposure => fills non-decreasing
    # (same band threshold in weight units; larger targets cross the band at
    # least as often) and full-path DD ordering is finite. Check fills monotone
    # and that t010 < t025 monthly ordering is finite (no NaN).
    for sc in ("normal", "fee_stress", "execution_stress"):
        fills = [sum(y["fills"] for y in d[k][sc]["yearly"]) for k in TARGET_KEYS]
        assert all(f > 0 for f in fills), (sc, fills)
        assert fills == sorted(fills), (sc, fills)
        nets = [d[k][sc]["monthly_pct"] for k in TARGET_KEYS]
        assert all(np.isfinite(v) for v in nets), (sc, nets)
