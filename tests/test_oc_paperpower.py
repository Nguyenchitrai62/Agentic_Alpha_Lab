"""Tests for oc_paperpower (go-live gate power / false-pass analysis)."""

import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_paperpower"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _mod():
    spec = importlib.util.spec_from_file_location(
        "oc_paperpower_analyze", HERE / "analyze_paperpower.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_g2_baseline_reproduces_to_digit():
    out = _res()
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0 = out["g2_baseline"]
    assert g0["R"] == exp["R"] and g0["W"] == exp["W"] and g0["DD"] == exp["DD"]
    assert [yy["R"] for yy in g0["years"]] == [r for r, _ in exp["years"]]
    assert [yy["DD"] for yy in g0["years"]] == [d for _, d in exp["years"]]
    assert g0["full_path_dd"]["full"] == exp["full_path_dd"]


def test_carry_f025_matches_oc_carrycompound():
    out = _res()
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    g1 = out["g2_carry_f025"]
    ref = cc["rows"]["G2_f0.25"]
    assert g1["R"] == ref["R"] and g1["W"] == ref["W"] and g1["DD"] == ref["DD"]
    assert g1["full_path_dd"] == ref["full_path_dd"]
    assert [y["R"] for y in g1["years"]] == [y["R"] for y in ref["years"]]
    assert g1["carry_add_pp_per_month"] == cc["carry_add_pp_per_month"] == 0.224


def test_daily_stats_sane_and_truncated():
    out = _res()
    d = out["daily_stats"]
    assert d["n"] == 1825
    assert d["start"] == "2021-09-24" and d["end"] == "2026-09-23"
    assert np.isfinite(d["mu_daily"]) and d["mu_daily"] > 0
    assert np.isfinite(d["vol_daily"]) and d["vol_daily"] > 0
    assert d["min_daily"] < 0 < d["max_daily"]
    # S_neg shift constant matches the pre-registered monthly definition
    assert abs(d["mu_neg_daily"] - ((1 - 0.01) ** (1 / 30.4167) - 1)) < 1e-12


def test_power_rates_ordered_and_recommendation():
    out = _res()
    tab = out["power"]["block10"]
    for h in ("8w", "12w", "26w", "52w"):
        rows = tab[h]["rows"]
        ps = [rows[s]["pass_rate"] for s in ("S_good", "S_half", "S_zero", "S_neg")]
        ss = [rows[s]["stop_rate"] for s in ("S_good", "S_half", "S_zero", "S_neg")]
        assert all(0.0 <= x <= 1.0 for x in ps + ss)
        assert ps[0] > ps[1] > ps[2] > ps[3], (h, ps)
        assert ss[0] < ss[1] < ss[2] < ss[3], (h, ss)
    # headline finding: 8w and 12w weak, 26w first under 20 %
    assert tab["8w"]["rows"]["S_zero"]["pass_rate"] > 0.20
    assert tab["12w"]["rows"]["S_zero"]["pass_rate"] > 0.20
    assert tab["26w"]["rows"]["S_zero"]["pass_rate"] <= 0.20
    assert tab["52w"]["rows"]["S_zero"]["pass_rate"] <= 0.05
    assert out["recommendation"]["horizon"] == "26w"
    # sensitivity repeats the pattern
    s30 = out["power"]["block30"]
    assert s30["8w"]["rows"]["S_zero"]["pass_rate"] > 0.20
    assert s30["26w"]["rows"]["S_zero"]["pass_rate"] <= 0.20
    # reference cuts rise with horizon (edge compounds)
    p20 = [tab[h]["p20_cumret_pct"] for h in ("8w", "12w", "26w", "52w")]
    p5 = [tab[h]["p5_cumret_pct"] for h in ("8w", "12w", "26w", "52w")]
    assert p20 == sorted(p20) and p5 == sorted(p5)


def test_causality_truncation_and_no_heavy():
    src = (HERE / "analyze_paperpower.py").read_text()
    assert 'side="left"' in src  # last CLOSED bar strictly before t
    assert "strictly before" in src
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "eu.simulate", "phase_offset_full", "Pool(", "torch"):
        assert bad not in src, bad
    out = _res()
    assert out["meta"]["dd_note"].startswith("daily-close DD only")
    assert "regime persistence" in out["meta"]["caveat"]
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("strictly\nbefore", "E[d]", "no selection feeds back"):
        assert needle in rep, needle


def test_synthetic_hand_checked_cases():
    mod = _mod()
    # all-zero daily returns: every path has C = 0 and DD = 0 whatever the seed
    C, DD = mod.simulate(np.zeros(500), 56, 10, 200, 0)
    assert np.all(C == 0.0) and np.all(DD == 0.0)
    # constant +1 %/day over 10 days: C = 1.01^10 - 1, DD = 0
    C, DD = mod.simulate(np.full(500, 0.01), 10, 10, 100, 0)
    assert np.allclose(C, 1.01 ** 10 - 1) and np.all(DD == 0.0)
    # hand DD math on a fixed return path [0.1, -0.5, 0.1]:
    # P = [1.1, 0.55, 0.605], peak = [1, 1.1, 1.1, 1.1] -> DD = 1 - 0.55/1.1
    R = np.array([[0.1, -0.5, 0.1]])
    P = np.cumprod(1.0 + R, axis=1)
    full = np.concatenate([np.ones((1, 1)), P], axis=1)
    peak = np.maximum.accumulate(full, axis=1)[:, 1:]
    dd = float(np.max(1.0 - P / peak))
    assert abs(dd - 0.5) < 1e-12


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("38.3", "30.8", "13.7", "2.5", "26w", "+0.224",
                    "f = 0 reproduces", "most recent", "tiếng Việt"):
        assert needle in rep, needle
    plan = (HERE / "PLAN.md").read_text(encoding="utf-8")
    assert "S_zero PASS <= 20" in plan
