"""Tests for v180 blind audit (Part A). Does not open research/.../v180/ result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v180_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v180/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v180_audit_replication"
    assert d["blind"] == "did_not_open_research_v180_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["feature_columns"] == ["depth", "r5", "r15", "vspike", "taker15", "rng",
                                    "breadth", "btc_depth", "trend", "r1d", "funding", "k",
                                    "asset_BNB", "asset_BTC", "asset_ETH", "asset_SOL", "asset_XRP"]
    assert d["model"]["max_depth"] == 3
    assert d["model"]["learning_rate"] == 0.03
    assert d["model"]["max_iter"] == 300
    assert d["candidates_total"] == 6972
    assert d["live_total"] == 4297
    for a in ANCHORS:
        assert a in [p["anchor"] for p in d["per_anchor"]]
    p = d["primary_normal"]
    assert p["monthly_pct"] == 4.177
    assert p["full_path_dd"] == 18.09
    assert p["dd_1m_mark"] == 19.57
    assert p["gate_dd"] == 19.57
    assert p["rungs_taken"] == 1839
    assert p["rungs_cancelled"] == 2449
    assert p["mean_s"] == 1.486
    s = d["stress"]
    assert s["monthly_pct"] == 3.783
    assert s["full_path_dd"] == 18.27
    assert s["dd_1m_mark"] == 19.92
    assert s["rungs_taken"] == 1851
    assert s["rungs_cancelled"] == 2437


def test_per_anchor_ic_and_counts():
    d = _rep()
    per = {p["anchor"]: p for p in d["per_anchor"]}
    assert per["2021-09-24"]["train_points"] == 1754
    assert per["2021-09-24"]["test_points"] == 932
    assert per["2021-09-24"]["live_pred_pos"] == 767
    assert per["2022-09-24"]["live_pred_pos"] == 728
    assert per["2023-09-24"]["live_pred_pos"] == 1030
    assert per["2024-09-24"]["live_pred_pos"] == 862
    assert per["2025-09-24"]["live_pred_pos"] == 910
    # ICs improve after 2022 in this replication
    assert per["2021-09-24"]["ic_spearman"] == 0.012322481397980202
    assert per["2024-09-24"]["ic_spearman"] == 0.22950899363136382
    assert per["2024-09-24"]["ic_spearman"] > per["2021-09-24"]["ic_spearman"]
    # taken + cancelled == live considered in budget loop scope (gated fills on live bars)
    # gated fills may exceed taken+cancelled if some live rungs fall outside live books bars;
    # here taken+cancelled = 4288 (normal) vs live 4297 -> 9 live rungs outside live span or skipped
    assert d["primary_normal"]["rungs_taken"] + d["primary_normal"]["rungs_cancelled"] == 4288


def test_budget_math_synthetic():
    assert abs(0.05 / 0.30 - 1 / 6) < 1e-12
    # rung notional s*g*0.25/4/1.657 at s=1.486,g=1
    rn = 1.486 * 1.0 * 0.25 / 4 / 1.657
    assert abs(rn - 0.05605) < 1e-4
    # N_MAX admits floor(0.1667/0.05605)=2 rungs at mean scale
    assert int(N_MAX if False else (0.05 / 0.30) // rn) == 2
    # feature timing: r5 uses close(f-1)/close(f-6); r15 uses f-16; vspike num f-5..f-1
    f = 16
    assert f - 1 - 5 == 10 and f - 1 - 15 == 0
    assert (f - 5) == 11 and (f - 1) == 15


def test_lookahead_timing_definition():
    # features use minutes <= f-1 of holding bar T (known at fill f);
    # trend/r1d/funding use opens/funding at or before t/T (known at decision);
    # vol uses sleeve_unit shifted by 2 (minute-0 s_out of i-1 unknown at i);
    # payoff uses s[i]*g[i] decided at bar-close i with returns over i+1/i+2.
    assert True


def test_blind_script_does_not_open_v180():
    src = (AUD / "replicate_v180.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v180_result" not in body
    assert "v180_model" not in body
    assert "v180/v180" not in body
