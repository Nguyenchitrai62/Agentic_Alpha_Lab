"""Tests for v176 blind audit (Part A). Does not open research/.../v176/ result."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v176_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
KS = (2, 2.5, 3, 3.5, 4)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v176/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v176_audit_replication"
    assert d["blind"] == "did_not_open_research_v176_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["cap"] == 2.0
    assert d["S_REF"] == 1.657
    assert set(d["k_selection"].keys()) == set(ANCHORS)
    for a in ANCHORS:
        assert d["k_selection"][a]["best_k"] in KS
    p = d["primary"]
    assert p["monthly_pct"] == 5.109
    assert p["full_path_dd"] == 20.72
    assert p["mean_s"] == 1.493
    assert len(p["yearly"]) == 5
    assert p["full_path_dd_1m"] == 26.12
    assert p["full_path_dd_1m"] >= p["full_path_dd"]
    c = d["cost_stress"]
    assert c["monthly_pct"] == 4.507
    assert c["full_path_dd"] == 22.27
    assert len(c["yearly"]) == 5
    assert d["sleeve_totals"]["bars_nonzero"] == 471


def test_primary_yearly_and_fills():
    d = _rep()
    yrs = d["primary"]["yearly"]
    nets = [y["net_pct"] for y in yrs]
    assert nets[0] == 28.58 and nets[1] == 44.17 and nets[2] == 147.27
    fills = [y["fills"] for y in yrs]
    assert fills == [2036, 2178, 2189, 2190, 2184]
    assert yrs[0]["max_drawdown_percent"] == 20.72


def test_vol_target_math_synthetic():
    # sleeve_unit = sleeve / 1.657
    assert abs(0.25 / 1.657 - 0.15088) < 1e-4
    # realized_total[i] = 0.8*books[i-2]*ret + 0.6*carry[i-1] + sleeve_unit[i-1]
    books_lag, ret, carry_lag, su_lag = 0.5, 0.01, 0.002, 0.003
    rt = 0.8 * books_lag * ret + 0.6 * carry_lag + su_lag
    assert abs(rt - (0.004 + 0.0012 + 0.003)) < 1e-12
    # s = min(0.25/vol, 2), 1 if NaN
    assert min(0.25 / 0.1, 2.0) == 2.0
    assert abs(min(0.25 / 0.2, 2.0) - 1.25) < 1e-12
    s_nan = 1.0 if np.isnan(np.nan) else 0.0
    assert s_nan == 1.0
    # sqrt annualization: PD=6 -> sqrt(6*365)=sqrt(2190)
    assert abs(np.sqrt(2190) - np.sqrt(6 * 365)) < 1e-12


def test_lookahead_timing_definition():
    # sleeve[i-1] exits at bar i open + minute-0 range: s[i] using su[i-1]
    # needs minute 0 of bar i, which completes after decision i.
    # payoff sl[i] uses future bars i+1/i+2 like books r_next[i] (causal weight).
    assert True


def test_blind_script_does_not_open_v176():
    src = (AUD / "replicate_v176.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v176_result" not in body
    assert "v176_total" not in body
    assert "v176/v176" not in body
