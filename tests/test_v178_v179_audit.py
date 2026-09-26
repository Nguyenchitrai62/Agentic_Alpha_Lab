"""Tests for v178+v179 blind audit (Part A + Part B comparison).

Part A replication.json was saved before v178/ or v179/ was opened.
Part B tests may read v178/v178_result.json, v178/v178_diagnostics.json
and v179/v179_result.json for comparison.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v178_v179_audit")
REP = AUD / "replication.json"
V178D = Path("research/parallel/rounds/parallel-20260906-r2/v178/v178_diagnostics.json")
V178R = Path("research/parallel/rounds/parallel-20260906-r2/v178/v178_result.json")
V179R = Path("research/parallel/rounds/parallel-20260906-r2/v179/v179_result.json")
RUNGS = ("2.5", "3.0", "3.5", "4.0")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v178/v179 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v178_v179_audit_replication"
    assert d["blind"] == "did_not_open_research_v178_v179_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["cap"] == 2.0
    assert d["S_REF"] == 1.657
    assert d["params"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"].keys()) == {"v178_normal", "v178_stress", "v179_normal", "v179_stress"}
    r = d["rows"]["v178_normal"]
    assert r["monthly_pct"] == 5.508
    assert r["full_path_dd"] == 18.57
    assert r["full_path_dd_1m"] == 27.79
    assert r["worst_1m_time"] == "2025-10-10 16:00:00+00:00"
    assert np.isfinite(r["mean_s"]) and 0 < r["mean_s"] <= 2.0
    assert len(r["yearly"]) == 5
    rs = d["rows"]["v178_stress"]
    assert rs["monthly_pct"] == 4.789
    assert rs["full_path_dd"] == 19.23
    assert rs["full_path_dd_1m"] == 27.81
    assert d["ladder_fill_diagnostics_full_grid"]["fills_total"] == 7052
    assert d["ladder_fill_diagnostics_full_grid"]["fills_per_rung"] == {
        "2.5": 3024, "3.0": 1900, "3.5": 1259, "4.0": 869}
    n = d["rows"]["v179_normal"]
    assert n["taken_rungs_live"] == 891
    assert n["cancelled_rungs_live"] == 4293
    assert n["taken_rungs_live"] + n["cancelled_rungs_live"] == 5184
    ns = d["rows"]["v179_stress"]
    assert ns["taken_rungs_live"] == 894
    assert ns["cancelled_rungs_live"] == 4290


def test_v178_matches_fixed_diagnostics():
    d = _rep()
    v = json.loads(V178D.read_text())
    assert v["fixed_normal"]["monthly_pct"] == d["rows"]["v178_normal"]["monthly_pct"] == 5.508
    assert v["fixed_normal"]["full_path_dd"] == d["rows"]["v178_normal"]["full_path_dd"] == 18.57
    assert v["fixed_normal"]["dd_1m_mark"] == d["rows"]["v178_normal"]["full_path_dd_1m"] == 27.79
    assert v["fixed_normal"]["dd_1m_worst_bar"] == d["rows"]["v178_normal"]["worst_1m_time"]
    for a_y, v_y in zip(d["rows"]["v178_normal"]["yearly"], v["fixed_normal"]["yearly"]):
        assert a_y["net_pct"] == v_y["net_pct"]
        assert a_y["max_drawdown_percent"] == v_y["max_drawdown_percent"]
        assert a_y["fills"] == v_y["fills"]
    # stress matches up to the s_out+extra vs extra-as-fee accounting (<0.05pp yearly)
    assert abs(v["fixed_stress"]["monthly_pct"] - d["rows"]["v178_stress"]["monthly_pct"]) <= 0.002
    assert v["fixed_stress"]["full_path_dd"] == d["rows"]["v178_stress"]["full_path_dd"] == 19.23
    assert v["fixed_stress"]["dd_1m_mark"] == d["rows"]["v178_stress"]["full_path_dd_1m"] == 27.81
    vr = json.loads(V178R.read_text())
    assert vr["rungs"] == [2.5, 3.0, 3.5, 4.0]
    # primary (unfixed shift-1) differs from the shift-2 fixed row, as documented
    assert vr["primary_ladder"]["monthly_pct"] == 5.481
    assert v["fixed_normal"]["monthly_pct"] == 5.508


def test_v179_budget_fill_universe_matches_but_cap_differs():
    d = _rep()
    v = json.loads(V179R.read_text())
    assert abs(v["N_MAX"] - 0.05 / 0.30) < 1e-12
    # same fill universe: taken+cancelled live rungs identical
    assert d["rows"]["v179_normal"]["taken_rungs_live"] + d["rows"]["v179_normal"]["cancelled_rungs_live"] == \
        v["primary_normal"]["rungs_taken"] + v["primary_normal"]["rungs_cancelled"] == 5184
    # audit per-asset 0.05 + total 0.30 over-cancels vs leader total-only 1/6
    assert d["rows"]["v179_normal"]["taken_rungs_live"] == 891
    assert v["primary_normal"]["rungs_taken"] == 2055
    assert d["rows"]["v179_normal"]["taken_rungs_live"] < v["primary_normal"]["rungs_taken"]
    assert d["rows"]["v179_normal"]["monthly_pct"] == 3.938
    assert v["primary_normal"]["monthly_pct"] == 4.141


def test_budget_ordering_synthetic():
    # order: (fill minute, shallower rung, column BNB,BTC,ETH,SOL,XRP)
    fills = [(20, 1, 1), (18, 0, 4), (18, 0, 2), (20, 0, 0)]
    assert sorted(fills) == [(18, 0, 2), (18, 0, 4), (20, 0, 0), (20, 1, 1)]
    # N_MAX total-only cap: q=0.05, N_MAX=1/6 -> 3 rungs fit (0.15<=0.1666), 4th (0.20) cancelled
    q, nmax = 0.05, 0.05 / 0.30
    used, taken = 0.0, 0
    for _ in range(4):
        if used + q <= nmax + 1e-12:
            used += q
            taken += 1
    assert taken == 3
    # strict fill: equal is NOT a fill; bounds 16..238
    L = 97.0
    lows = np.full(240, 98.0)
    assert not bool((lows[16:239] < L).any())
    lows[16] = 96.9
    assert bool((lows[16:239] < L).any())
    # sleeve per bar = sum of 0.25/4 * r over 5x4 rungs
    r = np.full((5, 4), 0.01)
    assert abs(0.0625 * r.sum() - 0.0625 * 20 * 0.01) < 1e-15
    # vol shift-2: sleeve_unit[i-2] in realized; s = min(0.25/vol,2)
    assert abs(np.sqrt(2190) - np.sqrt(6 * 365)) < 1e-12
    assert min(0.25 / 0.1, 2.0) == 2.0


def test_blind_script_does_not_open_v178_v179():
    src = (AUD / "replicate_v178_v179.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v178_result" not in body
    assert "v179_result" not in body
    assert "v178_diagnostics" not in body
    assert "v178/v178" not in body
    assert "v179/v179" not in body
    assert "v178_limit_ladder" not in body
    assert "v179_stress_budget" not in body
    assert "shift(2)" in body or "shift(2)" in src
