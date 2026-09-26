"""Tests for v168 blind audit (Part A). Imports leader modules, does not open v168/."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v168_audit")
REP = AUD / "replication.json"
ROWS = ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v168/ folder"
    return json.loads(REP.read_text())


def _check_block(block):
    assert set(block.keys()) == set(ROWS)
    for r in ROWS:
        d = block[r]
        assert np.isfinite(d["monthly_pct"])
        assert 0.0 <= d["full_path_dd"] < 100
        assert len(d["yearly"]) == 5


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v168_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["v103"]["HS"] == [6, 18]
    assert d["v103"]["EMBARGO"] == 78
    assert d["v103"]["quantile"] == [0.25, 0.5, 0.75]
    _check_block(d["v168_quant"])
    _check_block(d["diagnostic_median_only"])
    for tag in ("A", "B", "D"):
        assert len(d["per_anchor"][tag]) == 5
        for row in d["per_anchor"][tag]:
            assert np.isfinite(row["c_ref"]) and row["c_ref"] > 0
            assert row["n_common"] > 1000
            assert row["n_test"] == 10950
            assert 0.5 <= row["mean_k"] <= 1.5
            assert row["ic_m_vs_y6"] is None or np.isfinite(row["ic_m_vs_y6"])
            assert row["ic_base_vs_y6"] is None or np.isfinite(row["ic_base_vs_y6"])
    assert d["shapes"]["union_bars"] == 10950


def test_quantile_math_synthetic():
    m = np.array([0.2, -0.1, 0.0])
    s = np.array([0.1, 0.05, 0.2])
    c_ref = 1.0
    k = np.clip((np.abs(m) / s) / c_ref, 0.5, 1.5)
    assert abs(k[0] - 1.5) < 1e-12  # 2.0 clipped
    assert abs(k[1] - 1.5) < 1e-12  # 2.0 clipped
    assert abs(k[2] - 0.5) < 1e-12  # 0.0 clipped
    spread = np.maximum(np.array([0.0005, 0.02]), 1e-3)
    assert abs(spread[0] - 1e-3) < 1e-15
    d = _rep()
    assert np.isfinite(d["v168_quant"]["primary_t25_governed"]["monthly_pct"])


def test_blind_script_imports_leaders_not_v168():
    src = (AUD / "replicate_v168.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "v144_deploy_v3" in body
    assert "v150_options_flow" in body or "opt_features" in body
    assert "v111_coinbase_premium" in body or "add_cb" in body
    assert "spec_from_file_location" in body
    assert 'loss="quantile"' in body or "loss='quantile'" in body or '"quantile"' in body
    assert "0.25" in body and "0.75" in body
    assert "clip" in body and "0.5, 1.5" in body
    assert "1e-3" in body
    assert "v168_quantile_confidence" not in body
    assert "v168_result" not in body
    assert "v168/v168" not in body
