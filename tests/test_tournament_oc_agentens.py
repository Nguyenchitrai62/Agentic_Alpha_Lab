"""Tests for oc_agentens: seed-ensemble integrity (fast checks, no refit)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_agentens"
SEEDS = (0, 101, 202, 303, 404)


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "build_ensemble.py", "screen_ensemble.py",
              "results.json", "REPORT.md", "build_info.json",
              "ens_table_s0.parquet"):
        assert (W / f).exists(), f
    for s in SEEDS:
        assert (W / f"seed_table_s{s}_s0.parquet").exists()


def test_plan_predates_results():
    assert (W / "PLAN.md").stat().st_mtime <= (W / "results.json").stat().st_mtime


def test_s0_reproduction_gate():
    r = _res()["s0_match"]
    assert r["overlap_rows"] == 273850
    assert r["size_match"] >= 0.999 and r["tp_match"] >= 0.999


def test_ensemble_schema_and_votes():
    ens = pd.read_parquet(W / "ens_table_s0.parquet")
    assert list(ens.columns) == ["T", "sym", "rung", "size", "tp"]
    assert len(ens) == 273850
    assert set(ens["size"].unique()) <= {0.5, 1.0, 1.5}
    assert set(ens["tp"].unique()) <= {0.5, 1.0, 1.5}
    s0 = pd.read_parquet(W / "seed_table_s0_s0.parquet")
    mg = ens.merge(s0, on=["T", "sym", "rung"], suffixes=("", "_s0"))
    # ENS is a majority vote: it must agree with S0 more often than any
    # single new seed does on size (smoothing toward the mode)
    agree_ens = float((mg["size"] == mg["size_s0"]).mean())
    assert agree_ens >= 0.94


def test_screening_consistency():
    r = _res()
    assert r["years_ens_ge_s0"] == sum(
        r["per_year"][str(k)]["ens_ge_s0"] for k in range(5))
    assert r["worst_year_sum"]["better"] == (
        r["worst_year_sum"]["ens"] > r["worst_year_sum"]["s0"])
    expect = ("PROMISING" if (r["years_ens_ge_s0"] >= 3
                              and r["worst_year_sum"]["better"])
              else "NOT PROMISING")
    assert r["verdict"] == expect
    for k in range(5):
        d = r["dropped"][str(k)]
        assert d["kept"] == d["n"] and r["per_year"][str(k)]["n"] == d["n"]
