"""audit_d1 tests: blind replication checks + look-ahead audit (each audit point has a test)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "research/tournament/audit_d1"
OCD = ROOT / "research/tournament/oc_downshare"
OCK = ROOT / "research/tournament/oc_kronoshidden"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_share_synthetic():
    """Hand-checked: downside-RV share windows + D1 assign_mult (our independent rule)."""
    bd = _load("build_d1", AUD / "build_d1.py")
    # all-down -> 1, all-up -> 0, symmetric -> 0.5, zero-vol -> NaN
    assert bd.share_of(np.array([-0.01] * 36)) == 1.0
    assert bd.share_of(np.array([0.01] * 36)) == 0.0
    assert abs(bd.share_of(np.array([0.01, -0.01] * 18)) - 0.5) < 1e-12
    assert not np.isfinite(bd.share_of(np.zeros(36)))
    assert not np.isfinite(bd.share_of(np.array([])))
    assert not np.isfinite(bd.share_of(np.array([0.01] * 35 + [np.nan])))
    # cross-check against oc_downshare tilt_rule on the same inputs
    tilt = _load("tilt_ocd", OCD / "tilt_rule.py")
    for rs in [np.array([-0.01] * 36), np.array([0.01] * 36),
               np.array([0.01, -0.01] * 18), np.zeros(36)]:
        a, b = bd.share_of(rs), tilt.share_of(rs)
        assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-12
    # D1 group helper: all-down closes -> 1 after burn-in, NaN before E=37
    closes = 100.0 * np.exp(np.cumsum(np.array([0.0] + [-0.01] * 40)))
    d1 = bd.d1_for_group(closes)
    assert bool(np.isnan(d1[:37]).all())
    assert abs(d1[37] - 1.0) < 1e-12
    eng = _load("eng_d1", AUD / "run_engine.py")
    assert eng.assign_mult(0.9, 1, 0.25, 0.68) == 1.25
    assert eng.assign_mult(0.1, 1, 0.25, 0.68) == 0.75
    assert eng.assign_mult(0.5, 1, 0.25, 0.68) == 1.0
    assert eng.assign_mult(float("nan"), 1, 0.25, 0.68) == 1.0
    assert eng.assign_mult(0.1, -1, 0.25, 0.68) == 1.25
    assert eng.assign_mult(0.9, -1, 0.25, 0.68) == 0.75
    assert eng.assign_mult(0.68, 1, 0.25, 0.68) == 1.25
    assert eng.assign_mult(0.25, 1, 0.25, 0.68) == 0.75
    for r, d in [(0.9, 1), (0.1, 1), (0.5, 1), (0.1, -1), (0.9, -1)]:
        assert eng.assign_mult(r, d, 0.25, 0.68) == tilt.assign_mult(r, d, 0.25, 0.68, 1.25, 0.75)


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
        assert bool((tr.t_exit < a - pd.Timedelta(days=7)).all())
        if a_str == "2025-09-24":
            assert bool((tr.t_exit < pd.Timestamp("2025-09-17", tz="UTC")).all())
        f0 = pd.read_parquet(AUD / "downshare_D1_4shift.parquet",
                             columns=["sym", "shift", "T", "risk_D1"])
        f0 = f0[f0["shift"] == 0]
        f0["T"] = pd.to_datetime(f0["T"], utc=True)
        dd = d.copy()
        dd["T"] = pd.to_datetime(dd["T"], utc=True)
        tr2 = dd[dd.sym.isin(harness.MAJORS) & (dd.t_exit < cut)]
        m = tr2.merge(f0, on=["sym", "T"], how="inner")
        m = m[m["risk_D1"].notna()]
        assert int(len(m)) == fit["n_joined"], (a_str, len(m), fit["n_joined"])


def test_shift_phase_mapping_grid():
    """Shift/phase mapping: per-shift feature T sits on that shift's 4h grid."""
    f = pd.read_parquet(AUD / "downshare_D1_4shift.parquet", columns=["shift", "T"])
    f["T"] = pd.to_datetime(f["T"], utc=True)
    for s in range(4):
        hh = f[f["shift"] == s]["T"].dt.hour.to_numpy()
        assert bool((((hh - s) % 4) == 0).all()), s
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    d = harness.load()
    f0 = pd.read_parquet(AUD / "downshare_D1_4shift.parquet",
                         columns=["sym", "shift", "T"])
    f0 = f0[f0["shift"] == 0]
    key = set(zip(f0["sym"], pd.to_datetime(f0["T"], utc=True).astype(str)))
    d["k2"] = list(zip(d["sym"], pd.to_datetime(d["T"], utc=True).astype(str)))
    cov = d[d.sym.isin(harness.MAJORS)]["k2"].isin(key).mean()
    assert cov > 0.90, cov


def test_multiplier_application_point():
    """Multiplier is applied inside sleeve_fill_size (per holding bar), budget unchanged."""
    src = (OCD / "run_engine.py").read_text()
    assert "mult * 1.7 * tilt(i, a) * base_size(i, a, r, f)" in src
    assert 'kw["sleeve_gross_cap"] = 2.0' in src
    assert 'kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7' in src
    assert "win_start=5" in src
    mine = (AUD / "run_engine.py").read_text()
    assert "mult * kd * tilt * base_size(i, a, r, f)" in mine
    assert 'kw["sleeve_gross_cap"] = 2.0' in mine
    assert "win_start=5" in mine


def test_feature_timing_truncation_recompute():
    """Feature timing: 200 random risk_D1 rows recomputed from bars truncated at T match."""
    res = json.loads((AUD / "tmp" / "truncation_check.json").read_text())
    assert res["n"] == 200
    assert res["pass_1e9"] is True
    assert res["max_abs_diff"] <= 1e-9, res
    src = (OCD / "build_downshare.py").read_text()
    assert "w = r[e - WIN_D1:e]" in src
    assert "e >= WIN_D1 + 1" in src
    esrc = (OCD / "run_engine.py").read_text()
    assert "T_arr = idx + pd.Timedelta(hours=4)" in esrc


def _oc_engine_numbers():
    """oc_downshare/results.json is not strict-JSON-parseable (bare text in
    a later field); extract the engine block with regex (engine numbers only)."""
    import re
    t = (OCD / "results.json").read_text(encoding="utf-8")
    def arr(key, variant):
        m = re.search(r'"' + variant + r'":\{"DDmax[^}]*?"years_DD":\[([^\]]+)\],"years_R":\[([^\]]+)\]',
                      t)
        # scoped search: find variant block inside dev4
        return m
    out = {}
    dev = t[t.find('"dev4"'):t.find('"last_scored_once"')]
    last = t[t.find('"last_scored_once"'):t.find('"reproduction"')]
    for variant in ("D1", "REF"):
        m = re.search(r'"' + variant + r'":\{"DDmax.*?"years_DD":\[([^\]]+)\],"years_R":\[([^\]]+)\]',
                      dev)
        assert m, variant
        out[(variant, "dev_dd")] = [float(x) for x in m.group(1).split(",")]
        out[(variant, "dev_r")] = [float(x) for x in m.group(2).split(",")]
        m2 = re.search(r'"' + variant + r'":\{"DDlast":([0-9.]+),"Rlast":([0-9.]+).*?"full_path_dd":([0-9.]+)',
                       last)
        assert m2, variant
        out[(variant, "ddlast")] = float(m2.group(1))
        out[(variant, "rlast")] = float(m2.group(2))
        out[(variant, "fulldd")] = float(m2.group(3))
    return out


def test_replication_matches_thresholds():
    """Quantitative comparison: R<=0.10pp, DD<=0.5pp, fits rel diff<=1e-6, feat<=1e-9."""
    rep = json.loads((AUD / "replication.json").read_text())
    occ = _oc_engine_numbers()
    fits_occ = json.loads((OCD / "fits.json").read_text())["D1"]
    for a, f in rep["fits"].items():
        g = fits_occ[a]
        assert f["direction"] == g["direction"], a
        for k in ("q20", "q80"):
            denom = max(abs(g[k]), 1e-12)
            assert abs(f[k] - g[k]) / denom <= 1e-6, (a, k, f[k], g[k])
        assert f["n_train"] == g["n_train_majors"], a
        assert f["n_joined"] == g["n_train_vol"], a
    dev_r = occ[("D1", "dev_r")]
    dev_dd = occ[("D1", "dev_dd")]
    ref_r = occ[("REF", "dev_r")]
    ref_dd = occ[("REF", "dev_dd")]
    for y in range(4):
        assert abs(rep["years_d1"][y]["R"] - dev_r[y]) <= 0.10, y
        assert abs(rep["years_d1"][y]["DD"] - dev_dd[y]) <= 0.5, y
        assert abs(rep["years_ref"][y]["R"] - ref_r[y]) <= 0.10, y
        assert abs(rep["years_ref"][y]["DD"] - ref_dd[y]) <= 0.5, y
    assert abs(rep["y4_d1"]["R"] - occ[("D1", "rlast")]) <= 0.10
    assert abs(rep["y4_d1"]["DD"] - occ[("D1", "ddlast")]) <= 0.5
    assert abs(rep["full_path_dd_d1"] - occ[("D1", "fulldd")]) <= 0.5
    assert abs(rep["full_path_dd_ref"] - occ[("REF", "fulldd")]) <= 0.5
    # features
    a = pd.read_parquet(AUD / "downshare_D1_4shift.parquet")
    b = pd.read_parquet(OCD / "downshare_features_4shift.parquet",
                        columns=["sym", "shift", "T", "risk_D1"])
    a["T"] = pd.to_datetime(a["T"], utc=True)
    b["T"] = pd.to_datetime(b["T"], utc=True)
    m = a.merge(b, on=["sym", "shift", "T"], how="inner", suffixes=("_us", "_th"))
    both_nan = m["risk_D1_us"].isna() & m["risk_D1_th"].isna()
    assert bool((m["risk_D1_us"].isna() == m["risk_D1_th"].isna()).all())
    d = (m.loc[~both_nan, "risk_D1_us"] - m.loc[~both_nan, "risk_D1_th"]).abs()
    assert float(d.max()) <= 1e-9, float(d.max())
