"""Tests for oc_g2k20compound (G2K20 + carry f=0.25, compounded method; f=0 exact; REPORT)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_g2k20compound"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"
G2K20R = ROOT / "research" / "diagnostics" / "oc_g2k20robust"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _get(r, scen, f):
    return next(c for c in r["combos"]
                if (c["scen"], c["f"]) == (scen, f))


def test_grid_complete_and_posthoc():
    r = _res()
    assert r["meta"]["row"] == "G2K20"
    assert r["meta"]["scens"] == ["base", "S1", "S2", "S3", "S4", "S5"]
    assert r["meta"]["f_rows"] == [0.0, 0.25]
    assert len(r["combos"]) == 6 * 2
    keys = {(c["scen"], c["f"]) for c in r["combos"]}
    assert len(keys) == 12
    assert r["meta"]["post_hoc"] is True and r["meta"]["reporting_only"] is True
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert "UNCHANGED" in r["meta"]["assumption"] or "oc_carrycompound" in r["meta"]["assumption"]
    assert "UTA" in r["meta"]["assumption"]
    assert len(r["side_by_side_g2carry"]) == 6


def test_f0_reproduces_all_six_g2k20_reference_rows():
    r = _res()
    rob = json.loads((G2K20R / "results.json").read_text())
    for scen in ("base", "S1", "S2", "S3", "S4", "S5"):
        c = _get(r, scen, 0.0)
        src = rob["baseline"] if scen == "base" else rob["configs"][scen]
        ry = [(y["R"], y["DD"]) for y in src["years"]]
        assert [y["R"] for y in c["years"]] == [x for x, _ in ry]
        assert [y["DD"] for y in c["years"]] == [d for _, d in ry]
        assert c["R_5y"] == src["mean5y"] and c["W"] == min(x for x, _ in ry)
        assert c["DD_maxyearly"] == src["maxDD"]
        assert c["full_path_dd"]["full"] == src["fullDD"]
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v422/v422_result.json").read_text())["rows"]["G2K20"]
    g0 = _get(r, "base", 0.0)
    assert (g0["R_5y"], g0["W"], g0["DD_maxyearly"]) == (exp["R"], exp["W"], exp["DD"])
    assert g0["full_path_dd"]["full"] == exp["full_path_dd"]


def test_compound_headlines():
    r = _res()
    assert (_get(r, "base", 0.25)["R_5y"], _get(r, "base", 0.25)["W"],
            _get(r, "base", 0.25)["DD_maxyearly"]) == (6.097, 3.021, 17.64)
    assert _get(r, "base", 0.25)["full_path_dd"]["full"] == 17.54
    assert (_get(r, "S1", 0.25)["R_5y"], _get(r, "S2", 0.25)["R_5y"],
            _get(r, "S3", 0.25)["R_5y"], _get(r, "S4", 0.25)["R_5y"],
            _get(r, "S5", 0.25)["R_5y"]) == (5.109, 5.913, 5.149, 5.546, 5.567)
    # compounding lift over the old book-keeping overlay (oc_g2k20robust carry_f025)
    rob = json.loads((G2K20R / "results.json").read_text())
    assert _get(r, "base", 0.25)["R_5y"] > rob["carry_f025"]["G2K20"]["base"]["R_5y"] == 5.989
    assert _get(r, "S1", 0.25)["R_5y"] > rob["carry_f025"]["G2K20"]["S1"]["R_5y"] == 5.022


def test_plain_answer_holds_ge5_ddlt20_everywhere():
    r = _res()
    for scen in ("base", "S1", "S2", "S3", "S4", "S5"):
        c = _get(r, scen, 0.25)
        assert c["r_ge_5"], scen
        assert c["dd_lt_20"], scen
        assert c["R_5y"] >= 5.0 and max(c["DD_maxyearly"], c["full_path_dd"]["full"]) < 20, scen
        assert c["losing_years"] == 0, scen
    # worst carry year is S1
    worst = min(("base", "S1", "S2", "S3", "S4", "S5"),
                key=lambda s: _get(r, s, 0.25)["R_5y"])
    assert worst == "S1" and _get(r, "S1", 0.25)["R_5y"] == 5.109


def test_side_by_side_dd_gaps_vs_g2carry():
    r = _res()
    fric2 = json.loads((ROOT / "research/tournament/oc_carryfric2/results.json").read_text())
    g2 = {(c["scen"], c["f"]): c for c in fric2["combos"] if c["row"] == "G2"}
    for s in r["side_by_side_g2carry"]:
        scen = s["scen"]
        k = _get(r, scen, 0.25)
        ref = g2[(scen, 0.25)]
        assert s["g2_carry"]["R_5y"] == ref["R_5y"]
        assert s["g2_carry"]["DD_maxyearly"] == ref["DD_maxyearly"]
        assert s["g2k20_carry"]["R_5y"] == k["R_5y"]
        assert abs(s["dd_gap_maxyearly"] - round(k["DD_maxyearly"] - ref["DD_maxyearly"], 2)) < 1e-9
        assert abs(s["dd_gap_full"] - round(k["full_path_dd"]["full"] - ref["full_path_dd"]["full"], 2)) < 1e-9
        # G2K20+carry costs more DD everywhere, earns more return everywhere
        assert s["dd_gap_maxyearly"] > 0 and s["dd_gap_full"] > 0, scen
        assert s["r_gap"] > 0, scen
    gaps = {s["scen"]: s["dd_gap_maxyearly"] for s in r["side_by_side_g2carry"]}
    assert gaps == {"base": 0.89, "S1": 0.57, "S2": 0.9, "S3": 0.59, "S4": 0.64, "S5": 0.65}


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
        assert c["dd_lt_20"] == (max(c["DD_maxyearly"], c["full_path_dd"]["full"]) < 20.0)
        assert c["r_ge_5"] == (c["R_5y"] >= 5.0)
        fac = 1.0
        for y in c["years"]:
            fac *= 1 + y["R"] / 100
        assert abs(fac ** (1 / 5) - 1 - c["R_5y"] / 100) < 5e-5
        for y in c["years"]:
            assert abs((y["end"]) ** (1 / 12) - 1 - y["R"] / 100) * 100 < 1e-2
        fp = c["full_path_dd"]
        assert fp["full"] == max(fp["marked"], fp["close"])
    for scen in ("base", "S1", "S3"):
        f0 = _get(r, scen, 0.0)
        f1 = _get(r, scen, 0.25)
        assert f1["R_5y"] > f0["R_5y"]
        assert f1["DD_maxyearly"] <= f0["DD_maxyearly"]
        assert f1["full_path_dd"]["full"] <= f0["full_path_dd"]["full"]


def test_causal_marking_and_no_heavy():
    src = (HERE / "analyze_g2k20compound.py").read_text()
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
    for probe in ("6.097", "5.109", "5.913", "5.149", "5.546", "5.567",
                  "17.64", "17.54", "+0.463", "+0.89", "YES"):
        assert probe in rep, probe
    for c in r["combos"]:
        assert str(c["R_5y"]) in rep
