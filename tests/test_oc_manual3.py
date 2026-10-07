"""Causality + accounting tests for oc_manual3 (no outcome tuning here)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_manual3"
sys.path.insert(0, str(OC))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import analyze_manual3 as A
import harness5 as H5

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")


def _results():
    return json.loads((OC / "results.json").read_text())


def test_n_matches_v399_definition():
    """Hand-computed n: exact-2.5-sigma flush counts, NaN skipped, own excluded."""
    O = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    SG = np.array([0.01, 0.01, 0.01, np.nan, 0.01])
    # b=1 exactly at threshold (100*(1-0.025)=97.5) counts; b=2 just above does not;
    # b=3 NaN sig skipped; b=4 flushed but is the OWN coin (excluded).
    C = np.array([90.0, 97.5, 97.51, 50.0, 10.0])
    assert A.count_n_row(O, C, SG, own=4) == 2  # b=0 and b=1
    assert A.count_n_row(O, C, SG, own=0) == 2  # b=1 and b=4
    C_all_ok = np.array([90.0, 90.0, 90.0, 90.0, 90.0])
    assert A.count_n_row(O, C_all_ok, SG, own=0) == 3  # b=1,b=2,b=4 (b=3 NaN, b=0 own)
    SG0 = np.array([0.0, 0.01, 0.01, 0.01, 0.01])
    assert A.count_n_row(O, C_all_ok, SG0, own=4) == 3  # zero-sig b=0 skipped


def test_recovery_rule_edges():
    rec, ok = A.recovery_and_pass(1.0, 0.5, 0.0)
    assert rec == pytest.approx(0.5) and ok is True
    rec, ok = A.recovery_and_pass(1.0, 0.9, 0.0)
    assert rec == pytest.approx(0.1) and ok is False
    rec, ok = A.recovery_and_pass(1.0, 1.2, 1.5)  # dynamic deepens
    assert rec is None and ok is False
    rec, ok = A.recovery_and_pass(1.0, 1.0, 1.0)  # no reduction
    assert rec is None and ok is False
    assert A.maxdd_of_cumsum(np.array([1.0, 1.0])) == pytest.approx(0.0)
    assert A.maxdd_of_cumsum(np.array([1.0, -2.0, 1.0])) == pytest.approx(3.0)


def test_decision_counts_match():
    r = _results()
    n_pass = 0
    for y in r["years"]:
        rec, ok = A.recovery_and_pass(y["DD_a"], y["DD_b"], y["DD_c"])
        assert ok == y["pass"]
        if rec is None:
            assert y["recovery"] is None
        else:
            assert rec == pytest.approx(y["recovery"], abs=1e-4)
        n_pass += bool(ok)
    assert r["decision"]["pass_years"] == f"{n_pass}/5" == "0/5"
    assert r["decision"]["promising"] is False


def test_static_embargo_and_fallbacks():
    """Year-1 pool = t_fill strictly < anchor - 7d; stored counts match."""
    g = pd.read_parquet(OC / "n_per_fill.parquet")
    g["t_fill"] = pd.to_datetime(g["t_fill"], utc=True)
    r = _results()
    a0 = ANCHORS[0]
    tr = g[g["t_fill"] < a0 - pd.Timedelta(days=7)]
    assert int(len(tr)) == r["years"][0]["n_train"] == 1345
    assert bool((tr["t_fill"] < a0 - pd.Timedelta(days=7)).all())
    # fallback recomputation: test-year fills whose cell has < 30 training fills
    te = g[(pd.to_datetime(g["T"], utc=True) >= a0)
           & (pd.to_datetime(g["T"], utc=True) < a0 + pd.Timedelta(days=365))
           & g["size_dep"].notna()]
    cell_n = tr.groupby(["sym", "x1"]).size()
    pool_n = tr.groupby(["x1"]).size()
    fb = 0
    for _, row in te.iterrows():
        if cell_n.get((row["sym"], row["x1"]), 0) >= 30:
            continue
        fb += 1  # cell miss -> pooled depth mean or neutral (both counted as fallback)
    assert fb == r["years"][0]["pooled_fallbacks"] == 104


def test_T_and_bounds():
    g = pd.read_parquet(OC / "n_per_fill.parquet")
    T = pd.to_datetime(g["T"], utc=True)
    assert bool((T < DEV_END).all())
    assert bool((pd.to_datetime(g["t_fill"], utc=True) < DEV_END).all())
    calc = pd.to_datetime(g["t_fill"], utc=True) - pd.to_timedelta(g["f"], unit="min")
    assert bool((calc == T).all())
    assert T.max() < DEV_END
    # 1m reads are single-coin files filtered strictly below DEV_END
    for s in MAJORS:
        for fp in A.coin_files(s):
            assert "1m" in fp.name
            assert ("klines" in fp.name) == (s == "BTCUSDT")


def test_universe_counts():
    r = _results()
    assert [y["n"] for y in r["years"]] == [990, 1045, 1330, 989, 1144]
    assert r["meta"]["grid_rows"] == 6876
    assert r["meta"]["test_rows"] == 5498
    assert [y["n_train"] for y in r["years"]] == [1345, 2335, 3401, 4743, 5704]
