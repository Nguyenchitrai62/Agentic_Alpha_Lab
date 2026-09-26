"""Tests for v171 blind audit Part A (fast; does not load 1m data, does not open v171/)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v171_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
KS = (2, 2.5, 3, 3.5, 4)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v171/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v171_audit_replication"
    assert d["blind"] == "did_not_open_research_v171_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["engine_real_reference"] == {"monthly_pct": 3.708, "full_path_dd": 18.87}
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
    comb = d["combined"]
    assert np.isfinite(comb["monthly_pct"])
    assert 0.0 <= comb["full_path_dd"] < 100
    assert len(comb["yearly"]) == 5


def test_baseline_gate_without_sleeve():
    d = _rep()
    assert d["engine_real_reference"]["monthly_pct"] == 3.708
    assert d["engine_real_reference"]["full_path_dd"] == 18.87
    # combined with the sleeve must differ from baseline (sleeve is live)
    assert d["combined"]["monthly_pct"] != 3.708
    assert d["sleeve_totals"]["events"] > 0


def test_trigger_entry_exit_math_synthetic():
    # trigger: first m in 16..238 with close/open(T)-1 <= -k*sigma
    sigma, k = 0.01, 3.0
    assert -k * sigma == -0.03
    dip = np.zeros(240)
    dip[16] = -0.029
    trig = next((m for m in range(16, 239) if dip[m] <= -k * sigma), -1)
    assert trig == -1  # above threshold, no event
    dip[20] = -0.031
    trig = next((m for m in range(16, 239) if dip[m] <= -k * sigma), -1)
    assert trig == 20
    assert trig + 1 <= 239  # entry minute exists inside the bar
    # entry/exit/fees: r = exit/entry - 1 - 0.001 - funding
    entry, exit_ = 100.0 * 1.0002, 101.0 * 0.9998
    funding = 0.0001
    r = exit_ / entry - 1 - 0.001 - funding
    assert abs(r - (100.9798 / 100.02 - 1 - 0.0011)) < 1e-12
    # sleeve per bar: 0.25 * sum over symbols
    assert abs(0.25 * (r + 0.0) - r / 4) < 1e-15


def test_selection_windows_definition():
    # selection [2020-02-01+30d, anchor-1d); applied [anchor, anchor+365d)
    import pandas as pd
    s0 = pd.Timestamp("2020-02-01", tz="UTC") + pd.Timedelta(days=30)
    assert str(s0.date()) == "2020-03-02"
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        assert (a0 - pd.Timedelta(days=1)) > s0
        assert (a0 + pd.Timedelta(days=365)) > a0
    # score = mean/std; bad std -> -inf (rejected)
    s = np.zeros(100)
    sd = float(s.std())
    score = float(s.mean()) / sd if sd > 0 else -np.inf
    assert score == -np.inf


def test_blind_script_does_not_open_v171():
    src = (AUD / "replicate_v171.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v154_books" in body
    assert "v171_result" not in body
    assert "v171_robustness" not in body
    assert "v171/v171" not in body
