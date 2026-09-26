"""Tests for v143 blind audit. No leader v143 evaluate/result code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v143_audit")
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def _load(name):
    p = AUD / name
    assert p.exists(), f"{name} must be saved by the audit scripts"
    return json.loads(p.read_text())


def test_reports_exist_and_pass():
    leak = _load("leakage_report.json")
    assert leak["verdict"] == "pass"
    assert leak["leaks_found"] == []
    assert all(leak["static"].values())
    for a in ANCHORS:
        d = leak["dynamic"][a]
        assert d["train_match"] and d["val_is_365d"] and d["test_is_365d"]
        assert d["max_tr_time_lt_anchor"] and d["min_te_time_ge_anchor"]
        assert d["gap_tr_end_to_val_start_bars"] >= 102 - 1e-9
    exp = _load("export_report.json")
    assert exp["verdict"] == "pass"
    assert exp["total_mismatched_cells"] == 0
    assert exp["max_abs_diff"] == 0.0
    assert exp["file_checks"]["rows_match"] and exp["file_checks"]["sha_match"]
    rep = _load("repro_report.json")
    assert abs(rep["diff_ic_nn_y6_cpu_minus_saved"]) <= 0.02
    assert rep["needs_explanation"] is False
    assert rep["info"]["train_steps"] == 15374 and rep["info"]["test_steps"] == 2190
    ev = _load("eval_report.json")
    assert ev["comparison"]["ic_match"] is True
    assert ev["comparison"]["ratio_match"] is True
    for key in ("primary_blend", "secondary_nn_only"):
        for sc in ("normal", "fee_stress", "execution_stress"):
            assert ev["comparison"][f"{key}.{sc}.monthly"]["diff"] == 0.0
            assert ev["comparison"][f"{key}.{sc}.fullDD"]["diff"] == 0.0


def test_cutoff_embargo_math():
    H4 = 4 * 3600 * 10**9
    for anchor in ("2021-09-24", "2025-09-24"):
        ns = pd.Timestamp(anchor, tz="UTC").value
        assert ns - 78 * H4 == (pd.Timestamp(anchor, tz="UTC") - pd.Timedelta(hours=312)).value
        assert ns - 102 * H4 == (pd.Timestamp(anchor, tz="UTC") - pd.Timedelta(hours=408)).value
    # per-target mask: label end t+(h+1)*4h >= cutoff -> masked
    cut = 1000
    for h in (6, 18, 42):
        t_ok = cut - (h + 1) * 4 - 1
        t_bad = cut - (h + 1) * 4
        assert (t_ok + (h + 1) * 4 >= cut) is False
        assert (t_bad + (h + 1) * 4 >= cut) is True
    # causal scale: first year ratio 1.0
    ev = _load("eval_report.json")
    assert ev["recomputed"]["nn_scale_ratio"]["2021-09-24"] == 1.0
    # blend formula spot-check on synthetic numbers
    hgb, nn, r = 0.1, 0.2, 1.5
    assert abs((0.5 * hgb + 0.5 * r * nn) - 0.2) < 1e-12


def test_eval_covers_all_scenarios_and_years():
    ev = _load("eval_report.json")
    for key in ("primary_blend", "secondary_nn_only"):
        for sc in ("normal", "fee_stress", "execution_stress"):
            assert len(ev["recomputed"][key][sc]["yearly"]) == 5
            for y in ev["recomputed"][key][sc]["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] > 0 and y["months"] == 12.0
    for a in ANCHORS:
        for k in ("hgb_y6", "nn_y6", "hgb_y18", "nn_y18"):
            v = ev["recomputed"]["ic"][a][k]
            assert np.isfinite(v) and -1.0 <= v <= 1.0


def test_cpu_prediction_file():
    p = AUD / "pred_2025-09-24_cpu.parquet"
    assert p.exists()
    df = pd.read_parquet(p)
    assert set(("t", "sym", "p6", "p18", "p42")) <= set(df.columns)
    assert set(df["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    assert len(df) == 10950  # 5 syms x 2190 test steps, all present
    assert df[["p6", "p18", "p42"]].notna().all().all()
    # IC eval rows are fewer (10930): tail labels not yet realized in the panel


def test_no_leader_v143_imports_in_blind_scripts():
    for name in ("leakage_check.py", "export_check.py"):
        src = (AUD / name).read_text()
        assert "v143_evaluate" not in src
        assert "v143_result" not in src
    # recompute reads v143_result.json only to compare after independent recompute
    # recompute must not import the leader evaluate module; retrain may use the kernel
    src = (AUD / "recompute_evaluate.py").read_text()
    assert "import v143" not in src and "from v143" not in src
    assert "train_v143" not in src  # recompute retrains HGBs itself
    rsrc = (AUD / "retrain_20250924_cpu.py").read_text()
    assert "train_v143.py" in rsrc or "train_v143" in rsrc  # expected: uses audited kernel
