"""Tests for oc_carryborrow (f=0.25 exact; borrow drag; causality)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carryborrow"
CCMP = ROOT / "research/tournament/oc_carrycompound"
CFR2 = ROOT / "research/tournament/oc_carryfric2"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _combo(scen, label):
    return next(c for c in _res()["combos"]
                if c["scen"] == scen and c["label"] == label)


def test_f025_reproduces_carrycompound_to_digit():
    ref = json.loads((CCMP / "results.json").read_text())["rows"]["G2_f0.25"]
    got = _combo("base", "f=0.25")
    assert [yy["R"] for yy in got["years"]] == [yy["R"] for yy in ref["years"]]
    assert [yy["DD"] for yy in got["years"]] == [yy["DD"] for yy in ref["years"]]
    assert got["R_5y"] == ref["R"] == 5.634
    assert got["W"] == ref["W"] == 2.778
    assert got["DD_maxyearly"] == ref["DD"] == 16.75
    assert got["full_path_dd"]["full"] == ref["full_path_dd"]["full"] == 16.66
    assert got["losing_years"] == 0
    assert got["borrow_apr"] is None


def test_s1_f025_reproduces_carryfric2():
    ref = next(c for c in json.loads((CFR2 / "results.json").read_text())["combos"]
               if (c["row"], c["scen"], c["f"]) == ("G2", "S1", 0.25))
    got = _combo("S1", "f=0.25")
    assert [yy["R"] for yy in got["years"]] == [yy["R"] for yy in ref["years"]]
    assert [yy["DD"] for yy in got["years"]] == [yy["DD"] for yy in ref["years"]]
    assert got["R_5y"] == ref["R_5y"] == 4.78
    assert got["W"] == ref["W"] == 2.147
    assert got["DD_maxyearly"] == ref["DD_maxyearly"] == 17.29
    assert got["full_path_dd"]["full"] == ref["full_path_dd"]["full"] == 17.22


def test_borrow_headlines_and_gains():
    out = _res()
    b10 = _combo("base", "f=0.5_apr10")
    b15 = _combo("base", "f=0.5_apr15")
    s10 = _combo("S1", "f=0.5_apr10")
    s15 = _combo("S1", "f=0.5_apr15")
    assert (b10["R_5y"], b10["W"], b10["DD_maxyearly"],
            b10["full_path_dd"]["full"]) == (5.569, 2.658, 16.93, 16.84)
    assert (b15["R_5y"], b15["W"], b15["DD_maxyearly"],
            b15["full_path_dd"]["full"]) == (5.424, 2.503, 17.1, 17.01)
    assert (s10["R_5y"], s10["W"], s10["DD_maxyearly"],
            s10["full_path_dd"]["full"]) == (4.696, 2.009, 17.47, 17.39)
    assert (s15["R_5y"], s15["W"], s15["DD_maxyearly"],
            s15["full_path_dd"]["full"]) == (4.55, 1.853, 17.64, 17.56)
    g = out["gain_table"]
    assert g["f=0.5_apr10/base"]["gain_vs_f025_pp"] == -0.065
    assert g["f=0.5_apr15/base"]["gain_vs_f025_pp"] == -0.21
    assert g["f=0.5_apr10/S1"]["gain_vs_f025_pp"] == -0.084
    assert g["f=0.5_apr15/S1"]["gain_vs_f025_pp"] == -0.23
    # borrow hurts return and adds DD everywhere, no new losing year
    for key in ("f=0.5_apr10/base", "f=0.5_apr15/base",
                "f=0.5_apr10/S1", "f=0.5_apr15/S1"):
        assert g[key]["gain_vs_f025_pp"] < 0
        assert g[key]["losing"] == 0
    # higher APR is worse than lower APR
    assert b15["R_5y"] < b10["R_5y"] and s15["R_5y"] < s10["R_5y"]
    assert b15["DD_maxyearly"] > b10["DD_maxyearly"]


def test_aggregates_and_borrow_accounting():
    out = _res()
    assert len(out["combos"]) == 6
    for c in out["combos"]:
        assert len(c["years"]) == 5
        assert min(y["R"] for y in c["years"]) == c["W"]
        assert max(y["DD"] for y in c["years"]) == c["DD_maxyearly"]
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"]) == 0
        fac = 1.0
        for y in c["years"]:
            fac *= 1 + y["R"] / 100
        assert abs(fac ** (1 / 5) - 1 - c["R_5y"] / 100) < 5e-5
        if c["borrow_apr"] is None:
            assert all(v == 0.0 for v in c["borrow_paid_year_acct"])
            assert c["borrow_paid_full_acct"] == 0.0
        else:
            assert all(v > 0 for v in c["borrow_paid_year_acct"])
            assert c["borrow_paid_full_acct"] > 0
            assert c["borrow_apr"] in (0.10, 0.15)


def test_causal_marking_and_no_heavy():
    src = (HERE / "analyze_carryborrow.py").read_text(encoding="utf-8")
    assert 'side="left"' in src
    assert "last CLOSED hourly bar strictly" in src
    assert "APR/8760" in src or "apr / HRS_YR" in src
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "phase_offset_full", "heavy_slot", "Pool("):
        assert bad not in src, bad
    meta = _res()["meta"]["assumption"]
    assert "UTA" in meta and "WHOLE" in meta


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("5.634", "5.569", "5.424", "4.78", "4.696", "4.55",
                   "-0.065", "-0.210", "-0.084", "-0.230",
                   "16.66", "16.84", "f=0.25", "reproduces oc_carrycompound",
                   "KHÔNG đáng", "f=0,25"):
        assert needle in rep, needle
