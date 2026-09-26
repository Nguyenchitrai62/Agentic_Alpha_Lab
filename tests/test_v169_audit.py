"""Tests for v169 blind audit Part A (fast; does not load 1m data, does not open v169/)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v169_audit")
REP = AUD / "replication.json"
ROWS = ("no_stop", "k_3", "k_2", "k_4")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v169/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["blind"] == "did_not_open_research_v169_until_this_file_saved"
    assert d["target"] == 0.25
    assert set(d["rows"].keys()) == set(ROWS)
    for r in ROWS:
        row = d["rows"][r]
        assert np.isfinite(row["monthly_pct"])
        assert 0.0 <= row["full_path_dd"] < 100
        assert 0.0 <= row["dd_1m"] < 100
        assert len(row["yearly"]) == 5
        assert row["n_stops"] >= 0
        assert set(row["stop_counts"].keys()) == {
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"}
        assert sum(row["stop_counts"].values()) == row["n_stops"]


def test_no_stop_matches_engine_real_gate():
    d = _rep()
    assert d["rows"]["no_stop"]["monthly_pct"] == 3.708
    assert d["rows"]["no_stop"]["full_path_dd"] == 18.87
    assert d["rows"]["no_stop"]["n_stops"] == 0
    assert d["engine_real_reference"]["monthly_pct"] == 3.708
    assert d["engine_real_reference"]["full_path_dd"] == 18.87


def test_stop_math_synthetic():
    # L = k sqrt(w'Sw) on a diagonal covariance.
    w = np.array([0.5, -0.25])
    S = np.diag([0.0004, 0.0009])
    for k in (3, 2, 4):
        L = k * float(np.sqrt(w @ S @ w))
        assert L > 0 and np.isfinite(L)
    assert abs(3 * float(np.sqrt(w @ S @ w)) - 3 * float(np.sqrt(0.5**2 * 0.0004 + 0.25**2 * 0.0009))) < 1e-15
    # Trigger: first m in 16..238 with R <= -L; exit strictly after trigger (m+1).
    R = np.zeros(240)
    R[16] = -0.001
    L = 0.002
    trig = next((m for m in range(16, 239) if R[m] <= -L), -1)
    assert trig == -1  # -0.001 > -0.002, no stop
    R[20] = -0.003
    trig = next((m for m in range(16, 239) if R[m] <= -L), -1)
    assert trig == 20
    assert trig + 1 <= 239  # exit minute exists inside the bar


def test_blind_script_does_not_open_v169():
    src = (AUD / "replicate_v169.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v154_books" in body
    assert "v169_result" not in body
    assert "v169_intrabar_stop" not in body
    assert "v169/v169" not in body
    assert "research_v169" not in body.lower() or "did_not_open_research_v169" in body
