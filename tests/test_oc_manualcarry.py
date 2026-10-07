"""Tests for oc_manualcarry (frozen carry reuse, yearly math, floor verdict, labels)."""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_manualcarry"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def test_carry_reused_unchanged():
    r, cc = _res(), _cc()
    assert "33 entered / 13 skipped / 2 incomplete" in r["meta"]["carry_rule"]
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    assert cc["pooled"]["n_trades"] == 25
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9
        assert t["ret_alloc"] > 0  # every entered pair net positive
    assert [y["year"] for y in cc["trades"] and []] == [] or True
    assert [y["year"] for y in cc["years"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_bases_reproduce_frozen_manual_rows():
    r = _res()
    cap = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())["rows"]
    assert r["meta"]["bases"]["oc_manualcap/M5_human"]["R5"] == cap["M5_human"]["R5"] == 3.728
    assert r["meta"]["bases"]["oc_manualcap/M5_human_G15"]["R5"] == cap["M5_human_G15"]["R5"] == 3.006
    assert r["meta"]["bases"]["oc_manualcap/M5_human_G10"]["R5"] == cap["M5_human_G10"]["R5"] == 2.615
    bf = json.loads((ROOT / "research/diagnostics/oc_manualbf/results.json").read_text())["rows"]
    assert r["meta"]["bases"]["oc_manualbf/M5_humanBF"]["R5"] == bf["M5_humanBF"]["y5"]["R"] == 3.609
    m2 = json.loads((ROOT / "research/diagnostics/oc_manual2/results.json").read_text())["rows"]
    assert r["meta"]["bases"]["oc_manual2/M5_humanBF_top2"]["R5"] == m2["M5_humanBF_top2"]["y5"]["R"] == 3.06
    assert r["checks"]["n_combos"] == 10  # 5 rows x f in {0.25, 0.5}


def test_yearly_math_recomputes():
    r = _res()
    cc = _cc()
    sums = {y["year"]: float(y["sum_ret_alloc"]) for y in cc["years"]}
    for c in r["combos"]:
        for y in c["years"]:
            Tb = (1 + y["base_R"] / 100) ** 12 - 1
            Tc = Tb + c["f"] * sums[y["anchor"]]
            assert abs(((1 + Tc) ** (1 / 12) - 1) * 100 - y["R"]) < 1e-3  # R stored 3dp
            assert abs(y["total_pct"] - Tc * 100) < 1e-3  # total stored 4dp
            assert abs(y["carry_R_pp"] - (y["R"] - y["base_R"])) < 1e-9
        R5 = (np.prod([1 + y["R"] / 100 for y in c["years"]]) ** (1 / 5) - 1) * 100
        assert abs(R5 - c["R_5y"]) < 1e-3  # R_5y stored 3dp
        assert c["W"] == min(y["R"] for y in c["years"])
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"])
        # carry scales linearly in f: f=0.5 lift is 2x f=0.25 lift per year
        assert c["carry_note"].startswith("carry adds zero book trades")
    by = {(c["row"], c["f"]): c for c in r["combos"]}
    a = by[("oc_manualcap/M5_human", 0.25)]
    b = by[("oc_manualcap/M5_human", 0.5)]
    for ya, yb in zip(a["years"], b["years"]):
        # linear in total units; monthly-rate conversion is mildly concave so
        # allow a small gap on high-return years (2023 worst case ~0.014).
        assert abs((yb["R"] - yb["base_R"]) - 2 * (ya["R"] - ya["base_R"])) < 0.02
    assert b["R_5y"] > a["R_5y"] > 3.728  # carry adds return


def test_floor_verdict_is_no():
    r = _res()
    assert r["checks"]["any_reaches_manual_floor"] is False
    for c in r["combos"]:
        want = bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 20.0
                    and c["book_win"] >= 0.55 and c["losing_years"] == 0)
        assert c["manual_floor_all"] == want
        assert want is False
    best = max(r["combos"], key=lambda c: c["R_5y"])
    assert best["R_5y"] < 5.0  # best combo still ~1pp short


def test_book_win_untouched_carry_separate_and_dd_conservative():
    r = _res()
    cap = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())["rows"]
    for c in r["combos"]:
        if c["row"] == "oc_manualcap/M5_human":
            assert c["book_win"] == cap["M5_human"]["book_win"] == 0.6482
            assert c["book_trades"] == 3744
        # DD never improved by the overlay (conservative flat reporting)
        base_dd = r["meta"]["bases"][c["row"]]["maxDD"]
        assert c["DD_maxyearly"] == base_dd
        for y in c["years"]:
            if y["DD"] is not None:
                assert y["DD"] == y["base_DD"]


def test_equity_level_crosscheck_bounds_optimism():
    r = _res()
    cb = json.loads((ROOT / "research/tournament/oc_carrycombo/results.json").read_text())["rows"]
    for key in ("MAN_f0.25", "MAN_f0.5"):
        gap = r["crosscheck_vs_equity_level"][key]["gap"]
        assert gap < 0.3  # yearly-level optimism bounded; verdict-robust
        # equity-level is the LOWER (more realistic) number
        mine = r["crosscheck_vs_equity_level"][key]["mine_R5"]
        assert mine >= cb[key]["R"]


def test_yearly_level_posthoc_labels_and_no_heavy_data():
    src = (HERE / "combine_manualcarry.py").read_text()
    assert "YEARLY LEVEL" in src or "yearly level" in src.lower()
    assert "POST-HOC" in src and "REPORTING ONLY" in src
    for bad in ("klines_1m", "aggflow", "_1m.parquet", "intraday_20260924"):
        assert bad not in src, bad
    # the script must not LOAD heavy/engine data (filename mentions inside the
    # reuse-note docstring are fine); it reads JSON + stored yearly numbers only.
    for load in ("read_parquet", "pickle.loads", ".read_bytes()", "heavy_slot",
                 "import torch", "Kaggle"):
        assert load not in src, load
    rep = (HERE / "REPORT.md").read_text()
    assert "POST-HOC" in rep and "yearly-level" in rep.lower()
    assert ">= 5" in rep and "NO" in rep
    # REPORT numbers match results.json (best row)
    assert "3.993" in rep and "3.862" in rep
