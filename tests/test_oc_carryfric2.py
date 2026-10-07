"""Tests for oc_carryfric2 (compounding carry x friction table; f=0 exact; REPORT)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carryfric2"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"
V421A = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421_audit"
D13R = ROOT / "research/diagnostics/oc_d13robust"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _get(r, row, scen, f):
    return next(c for c in r["combos"]
                if (c["row"], c["scen"], c["f"]) == (row, scen, f))


def test_grid_complete_and_posthoc():
    r = _res()
    assert r["meta"]["rows"] == ["G2", "D13BF"]
    assert r["meta"]["scens"] == ["base", "S1", "S2", "S3", "S4", "S5"]
    assert r["meta"]["f_rows"] == [0.0, 0.25]
    assert len(r["combos"]) == 2 * 6 * 2
    keys = {(c["row"], c["scen"], c["f"]) for c in r["combos"]}
    assert len(keys) == 24
    assert r["meta"]["post_hoc"] is True and r["meta"]["reporting_only"] is True
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert "UNCHANGED" in r["meta"]["assumption"] or "oc_carrycompound" in r["meta"]["assumption"]
    assert "UTA" in r["meta"]["assumption"]


def test_f0_reproduces_all_twelve_reference_rows():
    r = _res()
    rob_g2 = json.loads((V421A / "robust.json").read_text())
    rob_d13 = json.loads((D13R / "results.json").read_text())
    for row in ("G2", "D13BF"):
        for scen in ("base", "S1", "S2", "S3", "S4", "S5"):
            c = _get(r, row, scen, 0.0)
            if row == "G2":
                src = rob_g2["baseline"]["G2"] if scen == "base" else rob_g2["configs"][scen]
                ry, rmean, rdd, rfull = ([(y["R"], y["DD"]) for y in src["years"]],
                                         src["mean5y"], src["maxDD"], src["fullDD"])
            else:
                src = rob_d13["baseline"] if scen == "base" else rob_d13["configs"][scen]
                ry, rmean, rdd, rfull = ([(y["R"], y["DD"]) for y in src["years"]],
                                         src["mean5y"], src["maxDD"], src["fullDD"])
            assert [y["R"] for y in c["years"]] == [x for x, _ in ry]
            assert [y["DD"] for y in c["years"]] == [d for _, d in ry]
            assert c["R_5y"] == rmean and c["W"] == min(x for x, _ in ry)
            assert c["DD_maxyearly"] == rdd
            assert c["full_path_dd"]["full"] == rfull
    exp_g2 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0 = _get(r, "G2", "base", 0.0)
    assert (g0["R_5y"], g0["W"], g0["DD_maxyearly"]) == (exp_g2["R"], exp_g2["W"], exp_g2["DD"])
    assert g0["full_path_dd"]["full"] == exp_g2["full_path_dd"]
    exp_d13 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v424/v424_result.json").read_text())["rows"]["R2B1D13BF"]
    d0 = _get(r, "D13BF", "base", 0.0)
    assert (d0["R_5y"], d0["W"], d0["DD_maxyearly"]) == (exp_d13["R"], exp_d13["W"], exp_d13["DD"])
    assert d0["full_path_dd"]["full"] == exp_d13["full_path_dd"]


def test_compound_headlines_match_carrycompound_and_new_table():
    r = _res()
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    g = _get(r, "G2", "base", 0.25)
    assert (g["R_5y"], g["W"], g["DD_maxyearly"]) == (5.634, 2.778, 16.75)
    assert g["full_path_dd"]["full"] == 16.66
    assert g["R_5y"] == cc["rows"]["G2_f0.25"]["R"]
    # compounding lift over the year-start overlay (oc_carryfric) is ~+0.09pp
    fric = json.loads((ROOT / "research/tournament/oc_carryfric/results.json").read_text())
    old = next(c for c in fric["combos"] if (c["row"], c["scen"], c["f"]) == ("G2", "base", 0.25))
    assert g["R_5y"] > old["R_5y"] == 5.533
    # new-table spot values
    assert (_get(r, "G2", "S1", 0.25)["R_5y"], _get(r, "G2", "S2", 0.25)["R_5y"],
            _get(r, "G2", "S3", 0.25)["R_5y"], _get(r, "G2", "S4", 0.25)["R_5y"],
            _get(r, "G2", "S5", 0.25)["R_5y"]) == (4.78, 5.438, 4.806, 5.125, 5.111)
    assert (_get(r, "D13BF", "base", 0.25)["R_5y"], _get(r, "D13BF", "S2", 0.25)["R_5y"]) == (5.198, 5.02)
    assert (_get(r, "D13BF", "base", 0.25)["DD_maxyearly"],
            _get(r, "D13BF", "S2", 0.25)["DD_maxyearly"]) == (14.82, 14.92)


def test_plain_answers_hold():
    r = _res()
    keep_g2 = sorted(sc for sc in ("base", "S1", "S2", "S3", "S4", "S5")
                     if _get(r, "G2", sc, 0.25)["r_ge_5"])
    assert keep_g2 == ["S2", "S4", "S5", "base"]
    both_d13 = sorted(sc for sc in ("base", "S1", "S2", "S3", "S4", "S5")
                      if _get(r, "D13BF", sc, 0.25)["r_ge_5"]
                      and _get(r, "D13BF", sc, 0.25)["dd_lt_15"])
    assert both_d13 == ["S2", "base"]
    dd15 = sorted(sc for sc in ("base", "S1", "S2", "S3", "S4", "S5")
                  if _get(r, "D13BF", sc, 0.25)["dd_lt_15"])
    assert dd15 == ["S2", "base"]


def test_s1_carry_stress_math():
    r = _res()
    assert abs(r["checks"]["carry_extra_drag_S1"] - 0.00165) < 1e-12
    assert abs(r["checks"]["carry_fee_entry_paid_S1"] - (0.0015 + 0.0012)) < 1e-12
    assert r["checks"]["s1_min_stressed_ret_alloc"] > 0
    assert abs(r["checks"]["carry_fee_entry_paid_base"] - (0.001 + 0.00055)) < 1e-12
    cc = json.loads((CC / "results.json").read_text())
    assert len(cc["trades"]) == 33
    for t in cc["trades"]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9


def test_aggregates_consistent():
    r = _res()
    for c in r["combos"]:
        assert len(c["years"]) == 5
        assert min(y["R"] for y in c["years"]) == c["W"]
        assert max(y["DD"] for y in c["years"]) == c["DD_maxyearly"]
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"])
        assert c["dd_lt_15"] == (c["DD_maxyearly"] < 15.0)
        assert c["r_ge_5"] == (c["R_5y"] >= 5.0)
        fac = 1.0
        for y in c["years"]:
            fac *= 1 + y["R"] / 100
        assert abs(fac ** (1 / 5) - 1 - c["R_5y"] / 100) < 5e-5
        for y in c["years"]:
            assert abs((y["end"]) ** (1 / 12) - 1 - y["R"] / 100) * 100 < 1e-2
        fp = c["full_path_dd"]
        assert fp["full"] == max(fp["marked"], fp["close"])
    for row, scen in (("D13BF", "S3"), ("G2", "S1")):
        f0 = _get(r, row, scen, 0.0)
        f1 = _get(r, row, scen, 0.25)
        assert f1["R_5y"] > f0["R_5y"]
        assert f1["DD_maxyearly"] <= f0["DD_maxyearly"]
        assert f1["full_path_dd"]["full"] <= f0["full_path_dd"]["full"]


def test_causal_marking_and_no_heavy():
    src = (HERE / "analyze_carryfric2.py").read_text()
    assert 'side="left"' in src
    assert "last CLOSED hourly bar strictly" in src
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "phase_offset_full", "heavy_slot", "Pool("):
        assert bad not in src, bad
    q = pd.read_parquet(ROOT / "data/raw/qbasis_20261003/um_BTCUSDT_241227_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    qn = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    H = pd.Timestamp("2024-12-27 07:00", tz="UTC").value
    idx = int(np.searchsorted(qn, H, side="left") - 1)
    assert qn[idx] < H
    assert abs(float(q["close"].iloc[idx]) - 96650.0) < 1e-9


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    r = _res()
    assert "POST-HOC" in rep and "UNCHANGED" in rep
    for probe in ("5.634", "5.438", "5.125", "5.111", "4.780", "4.806",
                  "5.198", "5.020", "14.82", "14.92", "+0.224"):
        assert probe in rep, probe
    for c in r["combos"]:
        assert str(c["R_5y"]) in rep
