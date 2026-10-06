"""Tests for oc_g2k20folds (light diagnostic: G2 vs G2K20 selection-rule view)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/diagnostics/oc_g2k20folds"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _geo(rs):
    fac = 1.0
    for r in rs:
        fac *= 1 + r / 100
    return 100 * (fac ** (1 / len(rs)) - 1)


def test_sources_reproduced_to_digit():
    out = _res()
    v422 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v422/v422_result.json").read_text())["rows"]
    for key, row in (("G2", "R2B1D17BFG2"), ("G2K20", "G2K20"), ("REF_R2B1D17BF", "R2B1D17BF")):
        got, exp = out["without_carry"][key], v422[row]
        assert got["R_5y"] == exp["R"] and got["W_5y"] == exp["W"] and got["DD_5y"] == exp["DD"]
        assert got["full"] == exp["full_path_dd"]
        assert got["recent_R"] == exp["years"][4][0] and got["recent_DD"] == exp["years"][4][1]
    # f=0 cross-checks: carry inputs reproduce the same base rows
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())["rows"]
    assert [y["R"] for y in cc["G2_f0.0"]["years"]] == [r for r, _ in v422["R2B1D17BFG2"]["years"]]
    ck = json.loads((ROOT / "research/tournament/oc_g2k20compound/results.json").read_text())["combos"]
    f0 = next(c for c in ck if c["scen"] == "base" and c["f"] == 0.0)
    assert [y["R"] for y in f0["years"]] == [r for r, _ in v422["G2K20"]["years"]]
    assert out["meta"]["v421_G2_matches_v422_G2"] is True


def test_dev4_math_and_carry_inputs():
    out = _res()
    v422 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v422/v422_result.json").read_text())["rows"]
    for key, row in (("G2", "R2B1D17BFG2"), ("G2K20", "G2K20")):
        dev = [r for r, _ in v422[row]["years"][:4]]
        got = out["without_carry"][key]
        assert abs(_geo(dev) - got["dev4_mean"]) < 5e-4
        assert got["dev4_worst"] == min(dev)
        assert got["dev4_maxDD"] == max(d for _, d in v422[row]["years"][:4])
        assert got["dev4_losing"] == 0
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())["rows"]["G2_f0.25"]
    g = out["with_carry_compounded"]["G2_carry_compounded"]
    assert g["R_5y"] == cc["R"] == 5.634 and g["recent_R"] == 4.698 and g["recent_DD"] == 12.66
    assert g["dev4_mean"] == 5.87 and g["dev4_worst"] == 2.778 and g["dev4_maxDD"] == 16.75
    k = out["with_carry_compounded"]["G2K20_carry_compounded"]
    assert (k["R_5y"], k["recent_R"], k["recent_DD"]) == (6.097, 4.766, 13.41)
    assert (k["dev4_mean"], k["dev4_worst"], k["dev4_maxDD"]) == (6.433, 3.021, 17.64)


def test_fold4_fail_and_robust_pick():
    out = _res()
    f4 = out["fold4_fail"]
    assert (f4["fold"], f4["choice"], f4["good"]) == (4, "G2K20", False)
    assert (f4["test_R"], f4["test_DD"]) == (4.716, 13.65)
    assert (f4["ref_R"], f4["ref_DD"]) == (5.06, 12.81)
    assert f4["gap_R_pp"] == round(4.716 - 5.06, 3) == -0.344
    assert f4["gap_DD_pp"] == round(13.65 - 12.81, 3) == 0.84
    assert out["folds_from_manifest"]["2"]["good"] is True
    assert out["folds_from_manifest"]["3"]["good"] is False
    rp = out["robust_pick_dev_only"]
    assert rp["without_carry"] == "G2K20"
    assert "G2K20" in rp["with_carry_compounded"]
    assert rp["carry_changes_pick"] is False


def test_report_and_light_script():
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("5.601", "6.166", "2.832", "2.588", "-0.344", "0.84",
                   "does NOT change", "fold 4", "POST-HOC", "onsistency check"):
        assert needle in rep, needle
    src = (HERE / "recompute_folds.py").read_text()
    for bad in ("simulate(", "Pool(", "heavy_slot", "klines_1m", "phase_offset_full"):
        assert bad not in src, bad
