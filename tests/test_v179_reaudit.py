"""Tests for the v179 budget re-audit (OPENCODE_V179_REAUDIT.md).

Re-audit output: research/parallel/rounds/parallel-20260906-r2/v179_reaudit/re_audit.json
Leader reference: research/parallel/rounds/parallel-20260906-r2/v179/v179_result.json
Rule: ONE total-only cap N_MAX = 0.05/0.30 on the bar's total open sleeve
notional; NO per-asset cap; rn = s*g*0.0625/1.657; order (fill minute, rung,
asset column BNB,BTC,ETH,SOL,XRP); take while used + rn <= N_MAX + 1e-12.
"""
import json
from pathlib import Path

import numpy as np

REA = Path("research/parallel/rounds/parallel-20260906-r2/v179_reaudit")
OUT = REA / "re_audit.json"
SCRIPT = REA / "replicate_v179_budget_fix.py"
V179R = Path("research/parallel/rounds/parallel-20260906-r2/v179/v179_result.json")


def _audit():
    assert OUT.exists(), "run replicate_v179_budget_fix.py first"
    return json.loads(OUT.read_text())


def _leader():
    assert V179R.exists()
    return json.loads(V179R.read_text())


def test_reaudit_structure_and_rule():
    d = _audit()
    assert d["version"] == "v179_reaudit"
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["params"]["per_asset_cap"] is None
    assert set(d["rows"].keys()) == {"v179_normal", "v179_stress"}
    src = SCRIPT.read_text()
    assert "N_MAX" in src
    assert "PER_ASSET_CAP" not in src
    assert "shift(2)" in src


def test_normal_matches_leader():
    d = _audit()["rows"]["v179_normal"]
    v = _leader()["primary_normal"]
    assert d["monthly_pct"] == v["monthly_pct"] == 4.141
    assert d["full_path_dd"] == v["full_path_dd"] == 18.24
    assert d["full_path_dd_1m"] == v["dd_1m_mark"] == 19.81
    assert d["worst_1m_time"] == "2022-11-09 12:00:00+00:00"
    assert d["taken_rungs_live"] == v["rungs_taken"] == 2055
    assert d["cancelled_rungs_live"] == v["rungs_cancelled"] == 3129
    assert d["taken_rungs_live"] + d["cancelled_rungs_live"] == 5184
    assert d["mean_s"] == 1.486
    for a_y, v_y in zip(d["yearly"], v["yearly"]):
        assert a_y["anchor"] == v_y["anchor"]
        assert a_y["net_pct"] == v_y["net_pct"]
        assert a_y["max_drawdown_percent"] == v_y["max_drawdown_percent"]


def test_stress_matches_leader():
    d = _audit()["rows"]["v179_stress"]
    v = _leader()["stress"]
    assert d["monthly_pct"] == v["monthly_pct"] == 3.729
    assert d["full_path_dd"] == v["full_path_dd"] == 18.43
    assert d["full_path_dd_1m"] == v["dd_1m_mark"] == 20.72
    assert d["worst_1m_time"] == "2022-11-09 12:00:00+00:00"
    assert d["taken_rungs_live"] == v["rungs_taken"] == 2074
    assert d["cancelled_rungs_live"] == v["rungs_cancelled"] == 3110
    assert d["taken_rungs_live"] + d["cancelled_rungs_live"] == 5184
    assert d["mean_s"] == 1.484
    # stress yearly within the documented s_out+extra vs extra-as-fee delta
    for a_y, v_y in zip(d["yearly"], v["yearly"]):
        assert a_y["anchor"] == v_y["anchor"]
        assert abs(a_y["net_pct"] - v_y["net_pct"]) <= 0.02
        assert a_y["max_drawdown_percent"] == v_y["max_drawdown_percent"]


def test_budget_ordering_synthetic_total_only():
    # order: (fill minute, shallower rung, column BNB,BTC,ETH,SOL,XRP)
    fills = [(20, 1, 1), (18, 0, 4), (18, 0, 2), (20, 0, 0)]
    assert sorted(fills) == [(18, 0, 2), (18, 0, 4), (20, 0, 0), (20, 1, 1)]
    # N_MAX total-only: q=0.05 -> 3 rungs fit (0.15<=0.1666), 4th cancelled;
    # first rejection ends the bar since all rungs share q.
    q, nmax = 0.05, 0.05 / 0.30
    used, taken = 0.0, 0
    for _ in range(4):
        if used + q <= nmax + 1e-12:
            used += q
            taken += 1
        else:
            break
    assert taken == 3
    # typical audit q ~= s*g*0.0625/1.657 with s*g ~1.4 -> ~0.053; N_MAX fits 3
    q2 = 1.4 * 0.0625 / 1.657
    assert 0.05 < q2 < 0.06
    assert int(nmax // q2) == 3
    # rung notional formula spot check
    assert abs(1.5 * 1.0 * (0.25 / 4) / 1.657 - 1.5 * 0.0625 / 1.657) < 1e-15
    assert np.isfinite(np.sqrt(2190))
