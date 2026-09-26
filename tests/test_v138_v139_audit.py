"""Tests for v138+v139 blind audit (Part A). No leader v138/v139 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v138_v139_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v138/ or v139/ folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v138_v139_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    v138 = d["v138"]
    assert len(v138["anchors_v92"]) == 5 and len(v138["anchors_v94"]) == 5 and len(v138["anchors_v103"]) == 5
    for a in v138["anchors_v92"]:
        assert a["n_pred_rows"] == 5 * 2190, a
        assert a["train_rows"] > 30000
        for k in ("ic_hgb", "ic_ridge", "ic_blend"):
            assert k in a and np.isfinite(a[k]), (a["anchor"], k)
        assert a["sd_r"] > 0 and np.isfinite(a["sd_h"]) and np.isfinite(a["sd_r"])
    for a in v138["anchors_v94"]:
        assert a["n_pred_rows"] == 5 * 2190, a
        for k in ("ic_hgb", "ic_ridge", "ic_blend"):
            assert np.isfinite(a[k]), (a["anchor"], k)
    for a in v138["anchors_v103"]:
        assert a["n_pred_rows"] == 5 * 2190, a
        for k in ("ic_blend_vs_y6", "ic_blend_vs_y18"):
            assert np.isfinite(a[k]), (a["anchor"], k)
    for tag in ("hgb", "ridge", "blend"):
        assert tag in v138["scenarios"], tag
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = v138["scenarios"][tag][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] > 0 and y["months"] == 12.0
            assert 0.0 <= r["full_path_dd"] < 100 and np.isfinite(r["monthly_pct"])
    v139 = d["v139"]
    assert len(v139["anchors_v103"]) == 5
    for a in v139["anchors_v103"]:
        assert a["n_pred_rows"] == 5 * 2190, a
        assert 0.0 <= a["coverage"] <= 1.0
        assert np.isfinite(a["ic_vs_y6"]) and np.isfinite(a["ic_vs_y18"])
    assert len(v139["feats103_aug"]) == 36 + 8
    for f in ("pos_oi_chg6", "pos_oi_chg42", "pos_oi_z", "pos_top_ls",
              "pos_top_ls_chg6", "pos_top_ls_z", "pos_crowd_ls_z", "pos_taker_ls6"):
        assert f in v139["feats103_aug"], f
    cov = v139["coverage_panel"]
    assert 0.0 < cov["coverage_full"] < 1.0 and cov["n_full_pos"] > 10000
    for sc in ("normal", "fee_stress", "execution_stress"):
        r = v139["scenarios"][sc]
        assert len(r["yearly"]) == 5
        assert 0.0 <= r["full_path_dd"] < 100
    assert v139["union_bars"] == 5 * 2190


def test_pvol_matches_v129_and_blend_sane():
    d = _rep()
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    # blend scenarios sit between or near components; all three differ (diversity works)
    n = d["v138"]["scenarios"]
    assert n["hgb"]["normal"]["monthly_pct"] != n["ridge"]["normal"]["monthly_pct"]
    assert n["blend"]["normal"]["monthly_pct"] != n["hgb"]["normal"]["monthly_pct"]
    # v139 full-path DD is finite and yearly fills sane
    for y in d["v139"]["scenarios"]["normal"]["yearly"]:
        assert y["fills"] > 1000


def test_selection_guards_in_code():
    src = (AUD / "replicate_v138_v139.py").read_text()
    assert "Ridge(alpha=10" in src
    assert "merge_asof" in src and "tolerance" in src
    assert "minutes=5" in src
    assert "rolling(180" in src and "min_periods=90" in src
    assert "rolling(6" in src and "min_periods=3" in src
    assert "clip(-5, 5)" in src or "clip(-5,5)" in src
    assert "v138_result.json" not in src and "v139_result.json" not in src
    assert "import v138" not in src and "import v139" not in src
    assert "from v138" not in src and "from v139" not in src
