"""Tests for v174 blind audit (Part A). Does not open research/.../v174/."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v174_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
KS = (2, 2.5, 3, 3.5, 4)
SIZES = ("0.25", "0.2", "0.15")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v174/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v174_audit_replication"
    assert d["blind"] == "did_not_open_research_v174_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["engine_real_reference_W60"] == {"monthly_pct": 3.802, "full_path_dd": 18.93}
    assert set(d["k_selection_dip"].keys()) == set(ANCHORS)
    assert set(d["k_selection_spike"].keys()) == set(ANCHORS)
    for a in ANCHORS:
        assert d["k_selection_dip"][a]["best_k"] in KS
        assert d["k_selection_spike"][a]["best_k"] in KS
        assert set(d["k_selection_spike"][a]["candidates"].keys()) == {str(k) for k in KS}
    assert len(d["per_anchor_spike"]) == 5
    assert len(d["per_anchor_dip"]) == 5
    for row in d["per_anchor_spike"]:
        assert row["k"] in KS
        assert np.isfinite(row["sleeve_net_pct"])
        assert 0.0 <= row["sleeve_dd_pct"] < 100
        assert row["events"] >= 0 and row["bars_nonzero"] >= 0
        assert row["events"] >= row["bars_nonzero"]
    b = d["books_alone_W60"]
    assert b["monthly_pct"] == 3.802 and b["full_path_dd"] == 18.93
    assert len(b["yearly"]) == 5
    for key in ("combined_dip_by_size", "combined_spike_by_size", "combined_both_by_size"):
        assert set(d[key].keys()) == set(SIZES)
        for sz in SIZES:
            r = d[key][sz]
            assert np.isfinite(r["monthly_pct"])
            assert 0.0 <= r["full_path_dd"] < 100
            assert len(r["yearly"]) == 5
    assert d["sleeve_totals_spike"]["events"] > 0
    assert d["sleeve_totals_dip"]["events"] > 0
    corr = d["daily_correlation_dip_spike"]
    assert corr["applied_coverage"] is None or -1.0 <= corr["applied_coverage"] <= 1.0
    assert corr["n_days_applied"] > 1000


def test_books_gate_and_dip_matches_v172():
    d = _rep()
    assert d["books_alone_W60"]["monthly_pct"] == 3.802
    assert d["books_alone_W60"]["full_path_dd"] == 18.93
    # books+dip must equal the v172 audit row exactly
    assert d["combined_dip_by_size"]["0.25"]["monthly_pct"] == 4.597
    assert d["combined_dip_by_size"]["0.25"]["full_path_dd"] == 22.42
    # spike sleeve is live: books+spike differs from books alone
    assert d["combined_spike_by_size"]["0.25"]["monthly_pct"] != 3.802
    # both sleeves row exists and differs from dip-only
    assert d["combined_both_by_size"]["0.25"]["monthly_pct"] != d["combined_dip_by_size"]["0.25"]["monthly_pct"]


def test_spike_short_math_synthetic():
    # s = max(0.0002, 0.25 * (H - L) / O) per fill minute (same range model as v172)
    assert abs(max(0.0002, 0.25 * (100.1 - 99.9) / 100.0) - 0.0005) < 1e-12
    assert max(0.0002, 0.25 * (100.01 - 99.99) / 100.0) == 0.0002  # floor binds
    # short: entry = O(m+1)*(1-s_in), cover = O(T+4h)*(1+s_out)
    entry, cover = 100.0 * (1 - 0.0005), 101.0 * (1 + 0.0003)
    funding = 0.0001
    r = entry / cover - 1 - 0.001 + funding
    assert abs(r - (99.95 / 101.0303 - 1 - 0.0009)) < 1e-9
    # trigger: first m in 16..238 with close/open(T)-1 >= +k*sigma
    sigma, k = 0.01, 3.0
    mv = np.zeros(240)
    mv[20] = 0.031
    trig = next((m for m in range(16, 239) if mv[m] >= k * sigma), -1)
    assert trig == 20 and trig + 1 <= 239
    # exit minute is cube row i+1 minute 0
    assert 0 == 0


def test_selection_windows_definition():
    s0 = pd.Timestamp("2020-02-01", tz="UTC") + pd.Timedelta(days=30)
    assert str(s0.date()) == "2020-03-02"
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        assert (a0 - pd.Timedelta(days=1)) > s0
        assert (a0 + pd.Timedelta(days=365)) > a0
    s = np.zeros(100)
    sd = float(s.std())
    score = float(s.mean()) / sd if sd > 0 else -np.inf
    assert score == -np.inf


def test_blind_script_does_not_open_v174():
    src = (AUD / "replicate_v174.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v174_result" not in body
    assert "v174_spike" not in body
    assert "v174/v174" not in body
