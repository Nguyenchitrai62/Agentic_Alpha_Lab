"""v167 blind audit tests (Part A only; does not open research/.../v167/)."""
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research/parallel/rounds/parallel-20260906-r2/v167_audit"
PRED_DIR = ROOT / "artifacts/kaggle/v167/output/v167_out"
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pred_files_one_row_per_t_sym_no_nan():
    for a in ANCHORS:
        df = pd.read_parquet(PRED_DIR / f"pred_{a}.parquet")
        df["t"] = pd.to_datetime(df["t"], utc=True)
        a0 = pd.Timestamp(a, tz="UTC")
        e0 = a0 + pd.Timedelta(days=365)
        assert len(df) == 2190 * 5
        assert int(df.duplicated(["t", "sym"]).sum()) == 0
        assert int(df.isna().sum().sum()) == 0
        assert bool(((df["t"] >= a0) & (df["t"] < e0)).all())
        for k in ("p6", "p18", "p42", "p84"):
            assert f"gru_{k}" in df.columns


def test_replication_json_structure():
    rep = json.loads((AUDIT / "replication.json").read_text())
    assert rep["anchors"] == ANCHORS
    assert len(rep["file_checks"]) == 5
    assert all(c["dup"] == 0 and c["nan"] == 0 and c["in_range"] for c in rep["file_checks"])
    assert len(rep["ic_table"]) == 5
    for row in rep["ic_table"]:
        assert row["n"] == 10950
        for k in ("ic_gru_p6_vs_y6", "ic_gru_p42_vs_y"):
            assert row[k] is not None and abs(row[k]) < 0.5
    assert rep["union_bars"] == 10950
    for block in ("primary", "secondary_E"):
        assert block in rep
        for r in ("reference_t15_ungoverned", "t20_governed", "primary_t25_governed"):
            assert r in rep[block]
            assert "monthly_pct" in rep[block][r]
            assert "full_path_dd" in rep[block][r]
            assert len(rep[block][r]["yearly"]) == 5


def test_replicate_script_blind():
    src = (AUDIT / "replicate_v167.py").read_text()
    assert "rounds/parallel-20260906-r2/v167/v167_result" not in src
    assert "train_v167" not in src
    assert "v167_evaluate" not in src and "v167_export" not in src
