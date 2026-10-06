"""Tests for oc_carryfric (friction x carry overlay; reuse, accounting, REPORT)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carryfric"
C13 = ROOT / "research" / "tournament" / "oc_carryd13"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def _c13res():
    return json.loads((C13 / "results.json").read_text())


def _script():
    spec = importlib.util.spec_from_file_location(
        "combine_carryfric", HERE / "combine_carryfric.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_grid_complete_and_posthoc():
    r = _res()
    assert r["meta"]["rows"] == ["D13BF", "G2"]
    assert r["meta"]["scens"] == ["base", "S1", "S2", "S3", "S4", "S5"]
    assert r["meta"]["f_rows"] == [0.0, 0.25, 0.5]
    assert len(r["combos"]) == 2 * 6 * 3
    keys = {(c["row"], c["scen"], c["f"]) for c in r["combos"]}
    assert len(keys) == 36
    assert r["meta"]["post_hoc"] is True and r["meta"]["reporting_only"] is True
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert "UNCHANGED" in r["meta"]["combination"]


def test_carry_rule_reused_unchanged():
    r, cc = _res(), _cc()
    assert "33 entered / 13 skipped / 2 incomplete" in r["meta"]["carry_rule"]
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9


def test_f0_reproduces_base_and_references():
    r = _res()
    assert r["checks"]["f0_vs_year_reset_max_gap"] == 0.0
    assert r["checks"]["f0_vs_reference_max_R_gap"] == 0.0
    assert r["checks"]["f0_vs_reference_max_DD_gap"] == 0.0
    by = r["base_rows"]["D13BF/base"]
    assert (by["R_5y"], by["W"], by["DD"]) == (4.971, 2.485, 14.98)
    g2 = r["base_rows"]["G2/base"]
    assert (g2["R_5y"], g2["W"], g2["DD"]) == (5.41, 2.588, 16.91)
    # G2 friction range quoted in the assignment
    s1 = next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == ("G2", "S1", 0.0))
    s2 = next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == ("G2", "S2", 0.0))
    assert (s1["R_5y"], s2["R_5y"]) == (4.571, 5.212)


def test_d13bf_base_matches_carryd13_to_digit():
    r, old = _res(), _c13res()
    for f in (0.25, 0.5):
        new = next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == ("D13BF", "base", f))
        prev = next(c for c in old["combos"] if c["f"] == f)
        assert new["R_5y"] == prev["R_5y"] and new["W"] == prev["W"]
        assert new["DD_maxyearly"] == prev["DD_maxyearly"]
        assert new["full_path_dd_chained"] == prev["full_path_dd_chained"]
        for yn, yo in zip(new["years"], prev["years"]):
            assert yn["R"] == yo["R"] and yn["DD"] == yo["DD"]
            assert yn["anchor"] == yo["anchor"]


def test_s1_carry_stress_math():
    M = _script()
    assert abs(M.S1_EXTRA_DRAG - 0.00165) < 1e-12
    assert abs(M.S1_ENTRY_PAID - (0.0015 + 0.0012)) < 1e-12
    r = _res()
    assert r["checks"]["s1_min_stressed_ret_alloc"] > 0
    import pytest as _pt
    assert r["checks"]["carry_fee_entry_paid_base"] == _pt.approx(0.001 + 0.00055)


def test_hourly_mark_causal_spot_check():
    spec = importlib.util.spec_from_file_location(
        "combine_carryd13_causal", C13 / "combine_carryd13.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    d = h[h["sym"] == "BTCUSDT"].sort_values("t")
    times = d["t"].values.astype("datetime64[ns]").astype(np.int64)
    closes = d["close"].to_numpy(float)
    probe = pd.Timestamp("2024-01-15 12:00", tz="UTC").value
    full = M.last_close_before(times, closes, np.array([probe]))[0]
    trunc = d[d["t"] < pd.Timestamp("2024-01-15 12:00", tz="UTC")]
    tt = trunc["t"].values.astype("datetime64[ns]").astype(np.int64)
    part = M.last_close_before(tt, trunc["close"].to_numpy(float), np.array([probe]))[0]
    assert full == part
    assert full != closes[-1]


def test_aggregates_consistent():
    r = _res()
    for c in r["combos"]:
        assert len(c["years"]) == 5
        assert min(y["R"] for y in c["years"]) == c["W"]
        assert max(y["DD"] for y in c["years"]) == c["DD_maxyearly"]
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"])
        assert c["dd_lt_15"] == (c["DD_maxyearly"] < 15.0)
        assert c["r_ge_5"] == (c["R_5y"] >= 5.0)
        for y in c["years"]:
            m2 = (1 + y["total_pct"] / 100) ** (1 / 12) - 1
            assert abs(m2 * 100 - y["R"]) < 1e-2
            assert abs((y["R"] - y["base_R"]) - y["carry_R_pp"]) < 1e-3
        assert "zero trades" in c["win_rate_note"]
    assert r["checks"]["monthly_total_residual_pp"] < 1e-2
    # carry helps return and never hurts DD by more than noise here
    for row, scen in (("D13BF", "S3"), ("G2", "S1")):
        f0 = next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == (row, scen, 0.0))
        f5 = next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == (row, scen, 0.5))
        assert f5["R_5y"] > f0["R_5y"]
        assert f5["DD_maxyearly"] <= f0["DD_maxyearly"]


def test_plain_answers_hold():
    r = _res()

    def get(row, scen, f):
        return next(c for c in r["combos"] if (c["row"], c["scen"], c["f"]) == (row, scen, f))

    # (a) D13BF + carry keeps both bars only at base (both f) and S2 f=0.5
    keep_a = [(sc, f) for sc in ("base", "S1", "S2", "S3", "S4", "S5") for f in (0.25, 0.5)
              if get("D13BF", sc, f)["dd_lt_15"] and get("D13BF", sc, f)["r_ge_5"]]
    assert sorted(map(str, keep_a)) == sorted(map(str, [("base", 0.25), ("base", 0.5), ("S2", 0.5)]))
    # (b) G2 + carry keeps 5y >= 5.0 except S1 (all f) and S3 (all f) and S4/S5 f=0
    fail_b = [(sc, f) for sc in ("base", "S1", "S2", "S3", "S4", "S5") for f in (0.0, 0.25, 0.5)
              if not get("G2", sc, f)["r_ge_5"]]
    assert sorted(map(str, fail_b)) == sorted(map(str, [
        ("S1", 0.0), ("S1", 0.25), ("S1", 0.5),
        ("S3", 0.0), ("S3", 0.25), ("S3", 0.5),
        ("S4", 0.0), ("S5", 0.0)]))


def test_no_1m_and_no_engine():
    src = (HERE / "combine_carryfric.py").read_text()
    for bad in ("klines_1m", "aggflow", "_1m.parquet", "intraday_20260924", "premium_1m",
                "simulate(", "phase_offset_full", "heavy_slot"):
        assert bad not in src, bad


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    r = _res()
    assert "POST-HOC" in rep and "UNCHANGED" in rep
    assert "(a)" in rep and "(b)" in rep
    for probe in ("5.062", "14.80", "4.820", "4.853", "5.104", "5.654"):
        assert probe in rep, probe
    for c in r["combos"]:
        assert str(c["R_5y"]) in rep
