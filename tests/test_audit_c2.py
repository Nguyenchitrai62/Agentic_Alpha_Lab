"""audit_c2 tests: blind replication checks + look-ahead audit (each audit point has a test)."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "research/tournament/audit_c2"
OCC = ROOT / "research/tournament/oc_chronos"
OCK = ROOT / "research/tournament/oc_kronoshidden"
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_assign_mult_synthetic():
    """Hand-checked: C2 hi/lo assignment on both directions + NaN (our independent rule)."""
    eng = _load("eng_c2", AUD / "run_engine.py")
    # direction +1: high risk favourable
    assert eng.assign_mult(3.0, 1, 0.5, 2.0) == 1.25
    assert eng.assign_mult(0.1, 1, 0.5, 2.0) == 0.75
    assert eng.assign_mult(1.0, 1, 0.5, 2.0) == 1.0
    assert eng.assign_mult(float("nan"), 1, 0.5, 2.0) == 1.0
    # direction -1: low risk favourable
    assert eng.assign_mult(0.1, -1, 0.5, 2.0) == 1.25
    assert eng.assign_mult(3.0, -1, 0.5, 2.0) == 0.75
    assert eng.assign_mult(float("nan"), -1, 0.5, 2.0) == 1.0
    # boundary is inclusive (matches our c2_mult: >= q80, <= q20)
    assert eng.assign_mult(2.0, 1, 0.5, 2.0) == 1.25
    assert eng.assign_mult(0.5, 1, 0.5, 2.0) == 0.75
    # cross-check against oc_chronos tilt_rule on the same inputs
    tilt = _load("tilt_occ", OCC / "tilt_rule.py")
    for r, d in [(3.0, 1), (0.1, 1), (1.0, 1), (0.1, -1), (3.0, -1), (2.0, 1), (0.5, 1)]:
        assert eng.assign_mult(r, d, 0.5, 2.0) == tilt.assign_mult(r, d, 0.5, 2.0, 1.25, 0.75)


def test_training_row_cut_truncation():
    """Causality/truncation: fits use only rows with t_exit < A-7d (no test-year leakage)."""
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    d = harness.load()
    rep = json.loads((AUD / "replication.json").read_text())
    for a_str, fit in rep["fits"].items():
        a = pd.Timestamp(a_str, tz="UTC")
        cut = a - pd.Timedelta(days=7)
        tr = d[d.sym.isin(harness.MAJORS) & (d.t_exit < cut)]
        assert int(len(tr)) == fit["n_train"], (a_str, len(tr), fit["n_train"])
        assert bool((tr.t_exit < cut).all())
        # embargo: nothing within 7d before the anchor is used
        assert bool((tr.t_exit < a - pd.Timedelta(days=7)).all())
        # 2025 anchor: no row from the most-recent year in training exits
        if a_str == "2025-09-24":
            assert bool((tr.t_exit < pd.Timestamp("2025-09-17", tz="UTC")).all())
        # joined count matches (shift-0 ch_q10 present)
        f0 = pd.read_parquet(OCC / "chronos_features_4shift.parquet",
                             columns=["sym", "shift", "T", "ch_q10"])
        f0 = f0[f0["shift"] == 0]
        m = tr.merge(f0, left_on=["sym", "T"], right_on=["sym", "T"], how="inner")
        assert int(len(m)) == fit["n_joined"], (a_str, len(m), fit["n_joined"])


def test_shift_phase_mapping_grid():
    """Shift/phase mapping: per-shift feature T sits on that shift's 4h grid."""
    f = pd.read_parquet(OCC / "chronos_features_4shift.parquet", columns=["shift", "T"])
    f["T"] = pd.to_datetime(f["T"], utc=True)
    for s in range(4):
        hh = f[f["shift"] == s]["T"].dt.hour.to_numpy()
        assert bool((((hh - s) % 4) == 0).all()), s
    # engine lookup key (sym, shift, H=idx+4h) exists for the bulk of dev bars:
    # at least 90% of harness majors test rows join to shift-0 features
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    d = harness.load()
    f0 = pd.read_parquet(OCC / "chronos_features_4shift.parquet",
                         columns=["sym", "shift", "T"])
    f0 = f0[f0["shift"] == 0]
    key = set(zip(f0["sym"], pd.to_datetime(f0["T"], utc=True).astype(str)))
    d["k2"] = list(zip(d["sym"], pd.to_datetime(d["T"], utc=True).astype(str)))
    cov = d[d.sym.isin(harness.MAJORS)]["k2"].isin(key).mean()
    assert cov > 0.90, cov


def test_multiplier_application_point():
    """Multiplier is applied inside sleeve_fill_size (per holding bar), budget unchanged."""
    src = (OCC / "run_engine.py").read_text()
    assert "mult * 1.7 * tilt(i, a) * base_size(i, a, r, f)" in src
    assert 'kw["sleeve_gross_cap"] = 2.0' in src
    assert 'kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7' in src
    assert "win_start=5" in src
    # our independent engine uses the same point
    mine = (AUD / "run_engine.py").read_text()
    assert "mult * kd * tilt * base_size(i, a, r, f)" in mine
    assert 'kw["sleeve_gross_cap"] = 2.0' in mine
    assert "win_start=5" in mine


def test_feature_timing_truncation_recompute():
    """Feature timing: 200 random ch_q10 rows recomputed from bars truncated at T match."""
    res = json.loads((AUD / "tmp" / "truncation_check.json").read_text())
    assert res["n"] == 200
    assert res["n_over_1e3"] == 0, res
    assert res["pass_1e3"] is True
    # construction cites: context = 512 closes ending at the bar closing at T
    src = (OCC / "run_chronos_4shift.py").read_text()
    assert "logc[e[:, None] + np.arange(-P, 0)]" in src
    # engine lookup uses T=idx+4h on that shift only
    esrc = (OCC / "run_engine.py").read_text()
    assert "T_arr = idx + pd.Timedelta(hours=4)" in esrc


def test_replication_matches_thresholds():
    """Quantitative comparison: R<=0.10pp, DD<=0.5pp, fits rel diff<=1e-6."""
    rep = json.loads((AUD / "replication.json").read_text())
    occ = json.loads((OCC / "results.json").read_text())
    fits_occ = json.loads((OCC / "fits.json").read_text())
    # fits
    for a, f in rep["fits"].items():
        g = fits_occ[a]
        assert f["direction"] == g["direction"], a
        for k in ("q20", "q80"):
            denom = max(abs(g[k]), 1e-12)
            assert abs(f[k] - g[k]) / denom <= 1e-6, (a, k, f[k], g[k])
        assert f["n_train"] == g["n_train_majors"], a
        assert f["n_joined"] == g["n_train_chronos"], a
    # engine: dev years 0..3 C2 + last year C2 + REF
    for y in range(4):
        assert abs(rep["years_c2"][y]["R"] - occ["dev"]["C2"]["r"][y]) <= 0.10, y
        assert abs(rep["years_c2"][y]["DD"] - occ["dev"]["C2"]["dd"][y]) <= 0.5, y
        assert abs(rep["years_ref"][y]["R"] - occ["dev"]["REF"]["r"][y]) <= 0.10, y
        assert abs(rep["years_ref"][y]["DD"] - occ["dev"]["REF"]["dd"][y]) <= 0.5, y
    assert abs(rep["y4_c2"]["R"] - occ["last_year_scored_once"]["C2"]["Rlast"]) <= 0.10
    assert abs(rep["y4_c2"]["DD"] - occ["last_year_scored_once"]["C2"]["DDlast"]) <= 0.5
    assert abs(rep["full_path_dd_c2"] - occ["last_year_scored_once"]["C2"]["full_path_dd"]) <= 0.5
    assert abs(rep["full_path_dd_ref"] - occ["last_year_scored_once"]["REF"]["full_path_dd"]) <= 0.5
