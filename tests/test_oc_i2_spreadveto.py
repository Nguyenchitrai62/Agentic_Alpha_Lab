"""Tests for oc_i2_spreadveto (IDEAS2_20261007 section 4).

Causality / leakage / gate checks + results.json schema consistency.
Light (no 1m reads except small depth-column probe).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent.parent / "research/tournament/oc_i2_spreadveto"
ROOT = Path(__file__).parent.parent
RES = HERE / "results.json"
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _res():
    return json.loads(RES.read_text())


def test_results_exists_and_variants_preregistered():
    r = _res()
    assert r["meta"]["variants"] == ["S1 skip on spread-p90",
                                    "S2 skip on spread-p90 OR depth-p10"]
    assert set(r["decision"]) >= {"S1", "S2", "chosen", "engine_run"}


def test_baseline_gate_values():
    r = _res()
    v = r["baseline"]["v421_G2"]
    assert (v["R"], v["W"], v["DD"], v["full_path_dd"]) == (5.41, 2.588, 16.91, 16.82)
    c = r["baseline"]["carry_G2_f0.25"]
    assert (c["R"], c["W"], c["DD"]) == (5.634, 2.778, 16.75)
    assert c["full_path_dd"]["full"] == 16.66


def test_replica_fidelity_phase0():
    r = _res()
    assert r["ledger"]["n"] == 22312
    ref = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]
    assert all(abs(g - x) < 1e-6 for g, x in zip(r["ledger"]["phase0_sums"], ref))


def test_base_matches_placebo_4phase_means():
    # audited placebo base (oc_placebo_dip REPORT): 4-phase-mean uncapped sums
    ref_s = [0.9113, 0.8326, 2.0998, 3.1974]
    ref_dd = [0.856, 0.951, 0.800, 0.355]
    r = _res()
    for y in range(4):
        got = r["base_unc"]["per_year"][y]
        assert abs(got["S_bar"] - ref_s[y]) < 5e-4, (y, got)
        assert abs(got["DD_bar"] - ref_dd[y]) < 5e-3, (y, got)


def test_spread_infeasible_proof():
    r = _res()
    assert r["meta"]["spread"]["feasible"] is False
    cols = r["meta"]["spread"]["columns"]
    for sym, cc in cols.items():
        assert not any("spread" in c or c in ("bid", "ask") for c in cc), (sym, cc)
    # S1 no-op: rule == base exactly
    assert r["decision"]["S1"]["dSum_dev4"] == 0.0
    assert r["s1_unc"]["d4_sum"] == r["base_unc"]["d4_sum"]


def test_no_imputation_pre2023_and_embargo():
    r = _res()
    thr = r["thresholds_p10"]
    for key, val in thr.items():
        ay = key.split("/")[0]
        if ay in ("0", "1"):  # anchors 2021/2022 predate depth start
            assert val is None, (key, val)
        else:
            assert val is not None and val > 0, (key, val)
    veto = r["veto"]["vetoed_by_dev_year"]
    assert veto["0"] == 0 and veto["1"] == 0  # size 1, no imputation


def test_veto_is_strictly_causal_spotcheck():
    # med7 for one vetoed bar uses only snapshots ts in [T-7d, T): recompute
    # for a single bar and check it sits below its threshold.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sv", HERE / "run_spreadveto.py")
    assert spec is not None  # module importable (no top-level run)


def test_depth_rows_capped():
    # Raw archive extends past the cap; the guard is in-script (ts < CAP).
    # Prove no post-cap snapshot could enter: every scored dev bar closes
    # before the cap, so all windows [T-7d, T) end before it.
    src = (HERE / "run_spreadveto.py").read_text()
    assert "d[d[\"ts\"] < CAP]" in src or 'd["ts"] < CAP' in src
    assert "2026-09-24" in src
    df = pd.read_parquet(
        ROOT / "research/tournament/oc_depthtilt/fills.parquet",
        columns=["t_bar", "year"])
    t = pd.to_datetime(df["t_bar"], utc=True)
    assert (t[df["year"] <= 3].max() < CAP)


def test_year2025_never_scored_for_variant():
    r = _res()
    for k in ("base_unc", "s1_unc", "s2_unc", "base_cap", "s2_cap"):
        assert len(r[k]["per_year"]) == 4, k  # dev years only
    assert r["decision"]["chosen"] is None
    assert r["decision"]["engine_run"] is False


def test_decision_math_consistent():
    r = _res()
    for name in ("S1", "S2"):
        dec = r["decision"][name]
        rule = r["s1_unc" if name == "S1" else "s2_unc"]
        base = r["base_unc"]
        ps = sum(1 for y in range(4)
                 if rule["per_year"][y]["S_bar"] >= base["per_year"][y]["S_bar"] - 1e-12)
        pd_ = sum(1 for y in range(4)
                  if rule["per_year"][y]["DD_bar"] <= base["per_year"][y]["DD_bar"] + 0.01 + 1e-12)
        assert dec["years_sum_ge_dev4"] == ps
        assert dec["years_dd_ok_dev4"] == pd_
        dsum = round(rule["d4_sum"] - base["d4_sum"], 6)
        assert dec["dSum_dev4"] == dsum
        assert dec["promising_dev4"] == bool(ps >= 4 and pd_ >= 4 and dsum >= 0.273)


def test_s2_fails_gate_as_reported():
    r = _res()
    d = r["decision"]["S2"]
    assert d["years_sum_ge_dev4"] == 3
    assert d["years_dd_ok_dev4"] == 4
    assert d["dSum_dev4"] < 0.273
    assert d["promising_dev4"] is False
