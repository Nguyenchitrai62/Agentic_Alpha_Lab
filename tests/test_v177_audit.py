"""Tests for v177 blind audit (Part A + cap). Part A replication.json was
saved before v177/ was opened; these tests may read both for comparison."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v177_audit")
REP = AUD / "replication.json"
V177 = Path("research/parallel/rounds/parallel-20260906-r2/v177/v177_result.json")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
KS = (2, 2.5, 3, 3.5, 4)
COLS = ("BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v177/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v177_audit_replication"
    assert d["blind"] == "did_not_open_research_v177_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["S_REF"] == 1.657
    assert d["params"]["max_fills_per_bar"] == 2
    assert set(d["k_selection"].keys()) == set(ANCHORS)
    for a in ANCHORS:
        assert d["k_selection"][a]["best_k"] in KS
        assert set(d["k_selection"][a]["candidates"].keys()) == {str(k) for k in KS}
    assert len(d["sleeve_unit_per_anchor"]) == 5
    for row in d["sleeve_unit_per_anchor"]:
        assert row["k"] in KS
        assert np.isfinite(row["sleeve_unit_net_pct"])
        assert 0.0 <= row["sleeve_unit_dd_pct"] < 100
        assert row["events"] >= 0 and row["bars_nonzero"] >= 0
        # cap property: at most 2 kept fills per nonzero bar
        assert row["events"] >= row["bars_nonzero"]
        assert row["events"] <= 2 * row["bars_nonzero"]
    p = d["primary"]
    assert np.isfinite(p["monthly_pct"])
    assert 0.0 <= p["full_path_dd"] < 100
    assert len(p["yearly"]) == 5
    assert np.isfinite(p["mean_s"]) and 0 < p["mean_s"] <= 2.0
    assert np.isfinite(p["full_path_dd_1m"]) and p["full_path_dd_1m"] >= p["full_path_dd"]
    assert d["sleeve_totals"]["events_kept"] > 0
    assert d["cap_diagnostics"]["bars_gt2"]["4"] >= 0
    # stress row present (v176 exactly)
    assert np.isfinite(d["cost_stress"]["monthly_pct"])


def test_primary_matches_v177():
    d = _rep()
    v = json.loads(V177.read_text())
    assert d["primary"]["monthly_pct"] == v["primary_cap2"]["monthly_pct"] == 4.71
    assert d["primary"]["full_path_dd"] == v["primary_cap2"]["full_path_dd"] == 21.1
    assert d["primary"]["mean_s"] == v["primary_cap2"]["mean_scale"] == 1.606
    for audit_y, v_y in zip(d["primary"]["yearly"], v["primary_cap2"]["yearly"]):
        assert audit_y["net_pct"] == v_y["net_pct"]
        assert audit_y["max_drawdown_percent"] == v_y["max_drawdown_percent"]
        assert audit_y["anchor"] == v_y["anchor"]
    for a in ANCHORS:
        assert d["k_selection"][a]["best_k"] == v["chosen"][a]["k"] == 4.0
    for audit_s, v_s in zip(d["sleeve_unit_per_anchor"], v["sleeve_alone"]):
        assert audit_s["anchor"] == v_s["anchor"]
        assert audit_s["k"] == v_s["k"]
        assert audit_s["events"] == v_s["events"]


def test_cap_ordering_synthetic():
    # order fills by (minute, column order BNB,BTC,ETH,SOL,XRP), keep first 2
    fmin = np.array([20, 20, 18, 50, 18])  # BNB,BTC,ETH,SOL,XRP
    key = fmin * 10 + np.arange(5)
    order = np.argsort(key)
    rank = np.empty_like(order)
    rank[order] = np.arange(5)
    keep = rank < 2
    # minute 18: ETH (col 2) before XRP (col 4); minute 20: BNB before BTC
    assert list(order[:2]) == [2, 4]
    assert keep.tolist() == [False, False, True, False, True]
    # tie at same minute broken by column order
    f2 = np.array([30, 30, 30, 30, 30])
    key2 = f2 * 10 + np.arange(5)
    order2 = np.argsort(key2)
    assert list(order2) == [0, 1, 2, 3, 4]
    # strict fill: equal is NOT a fill; bounds 16..238
    L = 97.0
    lows = np.full(240, 98.0)
    assert not bool((lows[16:239] < L).any())
    lows[16] = 96.9
    assert bool((lows[16:239] < L).any())
    lows3 = np.full(240, 98.0)
    lows3[238] = 96.9
    assert bool((lows[16:239] < L).any())
    lows3[238] = 97.0
    assert not bool((lows3[16:239] < L).any())
    lows4 = np.full(240, 98.0)
    lows4[239] = 90.0  # offset 239 is outside 16..238
    assert not bool((lows4[16:239] < L).any())


def test_selection_windows_definition():
    s0 = pd.Timestamp("2020-02-01", tz="UTC") + pd.Timedelta(days=30)
    assert str(s0.date()) == "2020-03-02"
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        assert (a0 - pd.Timedelta(days=1)) > s0
        assert (a0 + pd.Timedelta(days=365)) > a0
    # capped sleeve keeps at most 2 per bar: synthetic bar with 5 fills
    r = np.array([0.01, -0.02, 0.03, 0.005, -0.01])
    kept_idx = [2, 4]  # earliest minutes tie-broken, example
    capped = np.zeros(5)
    capped[kept_idx] = r[kept_idx]
    assert abs(0.25 * capped.sum() - 0.25 * (0.03 - 0.01)) < 1e-15


def test_blind_script_does_not_open_v177():
    src = (AUD / "replicate_v177.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v177_result" not in body
    assert "v177_sleeve" not in body
    assert "v177/v177" not in body
    assert "MAX_FILLS_PER_BAR = 2" in body
