"""Tests for research/diagnostics/oc_bookscale (assignment OPENCODE_W_oc_bookscale)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "diagnostics" / "oc_bookscale"

ROWS = ("G2", "G2B11", "G2B12")
CFGS = ("base", "S1", "S3")
KEYS = ["%s/%s" % (r, c) for r in ROWS for c in CFGS]


def _load_script():
    spec = importlib.util.spec_from_file_location("oc_bookscale_mod", str(OC / "oc_bookscale.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _results():
    return json.loads((OC / "results.json").read_text())


def test_results_exists_and_schema():
    r = _results()
    assert r["version"] == "oc_bookscale"
    assert r["reproduced"] is True
    assert set(r["rows"]) == set(KEYS)
    assert set(r["carry_f025"]) == set(KEYS)
    for key in KEYS:
        row = r["rows"][key]
        for k in ("years", "mean5y", "worst", "maxDD", "fullDD", "losing",
                  "wins", "book_share_years", "book_share_5y", "budget",
                  "keep_5", "dd_lt_18"):
            assert k in row, (key, k)
        assert len(row["years"]) == 5
        for y in row["years"]:
            assert "R" in y and "DD" in y
        assert len(row["book_share_years"]) == 5
        for b in row["book_share_years"]:
            assert "book" in b and "sleeve" in b and "book_share" in b
        b = row["budget"]
        for k in ("max_gross_per_phase", "fills_total", "fills_near_cap",
                  "fills_over_cap", "near_share", "near_weight_share",
                  "liq", "mean_g", "risk_budget", "gross_cap"):
            assert k in b, (key, k)
        assert set(b["max_gross_per_phase"]) == {"0", "1", "2", "3"}
        c = r["carry_f025"][key]
        for k in ("f", "years", "R_5y", "W", "DD_maxyearly",
                  "full_path_dd_chained", "losing_years", "keep_5", "dd_lt_18"):
            assert k in c, (key, k)
        assert c["f"] == 0.25
        assert len(c["years"]) == 5
    assert "plain_answer" in r and "verdict" in r["plain_answer"]


def test_reproduction_matches_v421():
    r = _results()
    base = r["rows"]["G2/base"]
    assert base["mean5y"] == 5.41
    assert base["maxDD"] == 16.91
    assert base["fullDD"] == 16.82
    assert [y["R"] for y in base["years"]] == [2.588, 3.282, 6.045, 10.677, 4.648]


def test_aggregates_consistent():
    r = _results()
    for key in KEYS:
        row = r["rows"][key]
        Rs = [y["R"] for y in row["years"]]
        assert row["worst"] == min(Rs)
        assert row["maxDD"] == max(y["DD"] for y in row["years"])
        assert row["losing"] == sum(v < 0 for v in Rs)
        g = 1.0
        for v in Rs:
            g *= 1.0 + v / 100.0
        assert abs(100.0 * (g ** (1.0 / 5) - 1.0) - row["mean5y"]) < 1e-2
        assert row["keep_5"] == (row["mean5y"] >= 5.0)
        assert row["dd_lt_18"] == (row["maxDD"] < 18.0)
        # wins pooled consistency (stored rounded to 4dp)
        w = row["wins"]
        assert len(w["years"]) == 5
        for y in w["years"]:
            n = y["nb"] + y["nr"]
            if n:
                assert abs(y["win_all"] - round((y["wb"] + y["wr"]) / n, 4)) < 1e-9
        p = w["pooled"]
        n = p["nb"] + p["nr"]
        assert abs(p["win_all"] - round((p["wb"] + p["wr"]) / n, 4)) < 1e-9
        # book share bounds + 5y flow consistency
        for b in row["book_share_years"]:
            assert b["book_share"] is None or 0.0 <= b["book_share"] <= 1.0
        b5 = sum(b["book"] for b in row["book_share_years"])
        s5 = sum(b["sleeve"] for b in row["book_share_years"])
        # yearly legs stored rounded to 4dp; allow rounding noise
        assert abs(row["book_share_5y"] - b5 / (b5 + s5)) < 5e-4
        # budget near_share consistency + cap enforced on the dip path
        bd = row["budget"]
        assert abs(bd["near_share"] - bd["fills_near_cap"] / bd["fills_total"]) < 5e-4
        assert bd["risk_budget"] == 0.26 * 1.7
        assert bd["gross_cap"] == 2.0
        for v in bd["max_gross_per_phase"].values():
            assert v <= 2.0 + 1e-9
        # carry combo consistency
        c = r["carry_f025"][key]
        assert c["W"] == min(y["R"] for y in c["years"])
        assert c["DD_maxyearly"] == max(y["DD"] for y in c["years"])
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"])
        assert c["keep_5"] == (c["R_5y"] >= 5.0)
        assert c["dd_lt_18"] == (c["DD_maxyearly"] < 18.0)
        for y in c["years"]:
            assert abs((y["R"] - y["base_R"]) - y["carry_R_pp"]) < 1e-3
            assert abs((y["DD"] - y["base_DD"]) - y["carry_DD_pp"]) < 1e-9


def test_year_of_windows_hand_checked():
    m = _load_script()
    assert m.year_of(pd.Timestamp("2022-01-01", tz="UTC")) == 0
    assert m.year_of(pd.Timestamp("2022-09-24", tz="UTC")) == 0
    assert m.year_of(pd.Timestamp("2022-09-25", tz="UTC")) == 1
    assert m.year_of(pd.Timestamp("2026-09-23", tz="UTC")) == 4
    assert m.year_of(pd.Timestamp("2026-09-24", tz="UTC")) == 4
    assert m.year_of(pd.Timestamp("2021-09-24", tz="UTC")) is None
    # leap-day gap joins year 3
    assert m.year_of(pd.Timestamp("2024-09-23 12:00", tz="UTC")) == 3


def test_cap_sweep_hand_checked():
    m = _load_script()
    T = pd.Timestamp("2022-01-01", tz="UTC")
    # two overlapping rungs w=1.0 each, then a third arriving at full concurrency
    pairs = [(T, T + pd.Timedelta(hours=8), 1.0),
             (T + pd.Timedelta(hours=1), T + pd.Timedelta(hours=9), 1.0),
             (T + pd.Timedelta(hours=2), T + pd.Timedelta(hours=3), 0.5)]
    cs = m.cap_sweep(pairs, G=2.0)
    assert cs["max_concurrent"] == 2.5
    assert cs["fills_total"] == 3
    # C before fills: 0, 1.0, 2.0 -> second (C+w=2.0) and third (2.5) are near;
    # only the third is strictly over G
    assert cs["fills_near_cap"] == 2
    assert cs["fills_over_cap"] == 1
    assert cs["fills_over_cap"] == 1
    # disjoint rungs never near the cap
    pairs2 = [(T, T + pd.Timedelta(hours=1), 0.1),
              (T + pd.Timedelta(hours=2), T + pd.Timedelta(hours=3), 0.1)]
    cs2 = m.cap_sweep(pairs2, G=2.0)
    assert cs2["max_concurrent"] == 0.1
    assert cs2["fills_near_cap"] == 0


def test_book_scale_wiring_present():
    src = (OC / "oc_bookscale.py").read_text()
    assert 'trade["book_mult"] = bm' in src
    assert '"G2B11"' in src and "1.1" in src
    assert '"G2B12"' in src and "1.2" in src
    # G2 harness pinned: kd 1.7, bear filter, G 2.0, inv rule
    assert "kd=1.7" in src or "kd\", 1.7" in src or '"kd", 1.7' in src or "kd" in src
    assert "sleeve_gross_cap" in src
    assert "sleeve_risk_budget" in src
    assert "rolling(1200" in src
    # frictions exactly as robust_v421
    assert "0.0004" in src and "0.0007 + 0.0005" in src
    assert "win_start=30" in src and "sleeve_start=31" in src
    assert "win_start=5" in src or "win_start\", 5" in src or "win_start" in src
    # attrib + reset metric + full-path mix
    assert "attrib" in src
    assert "year_reset" in src
    assert "v388.mix" in src or "v388m" in src or ".mix(" in src
    # carry method reuse, frozen rule
    assert "combine_carryd13" in src
    assert "last_close_before" in src
    assert len(json.loads((ROOT / "research/tournament/oc_cashcarry/results.json").read_text())["trades"]) == 33


def test_carry_reference_context():
    # oc_carryfric reference quoted in the assignment: G2+carry f=0.25 S1/S3 = 4.70/4.72
    ref = json.loads((ROOT / "research/tournament/oc_carryfric/results.json").read_text())
    s1 = next(c for c in ref["combos"] if (c["row"], c["scen"], c["f"]) == ("G2", "S1", 0.25))
    s3 = next(c for c in ref["combos"] if (c["row"], c["scen"], c["f"]) == ("G2", "S3", 0.25))
    assert round(s1["R_5y"], 2) == 4.70
    assert round(s3["R_5y"], 2) == 4.72


def test_plain_answer_matches_rule():
    r = _results()
    pa = r["plain_answer"]
    for row in ("G2B11", "G2B12"):
        alone = all(r["rows"]["%s/%s" % (row, cfg)]["keep_5"]
                    and r["rows"]["%s/%s" % (row, cfg)]["dd_lt_18"] for cfg in ("S1", "S3"))
        with_c = all(r["carry_f025"]["%s/%s" % (row, cfg)]["keep_5"]
                     and r["carry_f025"]["%s/%s" % (row, cfg)]["dd_lt_18"] for cfg in ("S1", "S3"))
        assert pa["verdict"][row]["alone"] == alone
        assert pa["verdict"][row]["with_carry"] == with_c
    rep = (OC / "REPORT.md").read_text()
    assert "Plain answer" in rep or "PLAIN" in rep or "verdict" in rep.lower()
    for key in KEYS:
        assert key in rep
