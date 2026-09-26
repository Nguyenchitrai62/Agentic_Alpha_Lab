"""Tests for v175 blind audit (Part A). Does not open research/.../v175/."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v175_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
KS = (2, 2.5, 3, 3.5, 4)
SIZES = ("0.25", "0.15")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v175/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v175_audit_replication"
    assert d["blind"] == "did_not_open_research_v175_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["engine_real_reference_W60"] == {"monthly_pct": 3.802, "full_path_dd": 18.93}
    assert set(d["k_selection"].keys()) == set(ANCHORS)
    for a in ANCHORS:
        assert d["k_selection"][a]["best_k"] in KS
        assert set(d["k_selection"][a]["candidates"].keys()) == {str(k) for k in KS}
    assert len(d["per_anchor"]) == 5
    for row in d["per_anchor"]:
        assert row["k"] in KS
        assert np.isfinite(row["sleeve_net_pct"])
        assert 0.0 <= row["sleeve_dd_pct"] < 100
        assert row["events"] >= 0 and row["bars_nonzero"] >= 0
        assert row["events"] >= row["bars_nonzero"]
    b = d["books_alone_W60"]
    assert b["monthly_pct"] == 3.802 and b["full_path_dd"] == 18.93
    assert len(b["yearly"]) == 5
    assert set(d["combined_by_size"].keys()) == set(SIZES)
    for key in SIZES:
        r = d["combined_by_size"][key]
        assert np.isfinite(r["monthly_pct"])
        assert 0.0 <= r["full_path_dd"] < 100
        assert len(r["yearly"]) == 5
    assert d["sleeve_totals"]["events"] > 0


def test_books_gate_and_sleeve_live():
    d = _rep()
    assert d["books_alone_W60"]["monthly_pct"] == 3.802
    assert d["books_alone_W60"]["full_path_dd"] == 18.93
    assert d["combined_by_size"]["0.25"]["monthly_pct"] != 3.802
    full = d["combined_by_size"]["0.25"]["monthly_pct"]
    small = d["combined_by_size"]["0.15"]["monthly_pct"]
    assert min(3.802, full) <= small <= max(3.802, full)


def test_limit_fill_math_synthetic():
    # L = open(T) * (1 - k*sigma); filled iff any low in 16..238 < L (strict)
    openT, sigma, k = 100.0, 0.01, 3.0
    L = openT * (1 - k * sigma)
    assert abs(L - 97.0) < 1e-12
    lows = np.full(240, 98.0)
    assert not bool((lows[16:239] < L).any())
    lows[20] = 96.99
    assert bool((lows[16:239] < L).any())
    lows2 = np.full(240, 98.0)
    lows2[30] = 97.0  # equal is NOT a fill (strict)
    assert not bool((lows2[16:239] < L).any())
    # r = exit/L - 1 - 0.0002 - 0.0005 - funding; s_out floor
    s_out = max(0.0002, 0.25 * (100.1 - 99.9) / 100.0)
    assert abs(s_out - 0.0005) < 1e-12
    assert max(0.0002, 0.25 * (100.01 - 99.99) / 100.0) == 0.0002
    exit_ = 101.0 * (1 - s_out)
    funding = 0.0001
    r = exit_ / L - 1 - 0.0002 - 0.0005 - funding
    assert abs(r - (100.9495 / 97.0 - 1 - 0.0008)) < 1e-9
    # sleeve per bar: 0.25 * sum over symbols
    assert abs(0.25 * (r + 0.0) - r / 4) < 1e-15


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


def test_blind_script_does_not_open_v175():
    src = (AUD / "replicate_v175.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v175_result" not in body
    assert "v175_limit" not in body
    assert "v175/v175" not in body
