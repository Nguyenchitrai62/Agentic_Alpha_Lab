"""Tests for oc_g2k20robust2 (light: no simulation, checks results.json + ROBUST.md)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_g2k20robust"
SCENS = ("S1", "S2", "S3", "S4", "S5")
REF_MEAN = 5.425
REF_FULLDD = 16.90


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "robust_g2k20.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()
    assert (D / "ROBUST.md").exists()
    for s in SCENS:
        assert (D / ("runs_G2K20_%s.pkl" % s)).exists()


def test_baseline_matches_v422_cache():
    r = _res()
    b = r["baseline"]
    assert r["row"] == "G2K20"
    assert r["spec"]["kd"] == 2.0 and r["spec"]["G"] == 2.0
    # v422_result.json G2K20: 5.874 mean, worst 2.832, maxDD 17.79, full 17.69
    assert abs(b["mean5y"] - 5.874) < 0.01
    assert abs(b["maxDD"] - 17.79) < 0.01
    assert abs(b["fullDD"] - 17.69) < 0.05
    assert len(b["years"]) == 5
    assert abs(b["years"][0]["R"] - 2.832) < 0.01
    assert abs(b["years"][4]["R"] - 4.716) < 0.01


def test_reference_numbers_match_robust_md():
    r = _res()
    rb = r["reference_R2B1D17BF"]["baseline"]
    assert abs(rb["mean5y"] - REF_MEAN) < 1e-9
    assert abs(rb["fullDD"] - REF_FULLDD) < 1e-9
    assert abs(r["reference_R2B1D17BF"]["configs"]["S1"]["mean5y"] - 4.58) < 1e-9


def test_configs_have_required_metrics():
    r = _res()
    for s in SCENS:
        m = r["configs"][s]
        assert len(m["years"]) == 5
        assert isinstance(m["mean5y"], float)
        assert isinstance(m["maxDD"], float)
        assert isinstance(m["fullDD"], float)
        # geometric-mean consistency with per-year R
        g = 1.0
        for y in m["years"]:
            g *= 1.0 + float(y["R"]) / 100.0
        assert abs(100.0 * (g ** 0.2 - 1.0) - m["mean5y"]) < 0.002
    assert r["configs"]["S5"]["year2021_short_window"] is True
    assert "s5_window" in r["configs"]["S5"]
    assert "baseline_same_window" in r["configs"]["S5"]


def test_report_verdict():
    rep = (D / "REPORT.md").read_text()
    assert "G2K20" in rep and "R2B1D17BF" in rep
    for s in SCENS:
        assert s in rep
    assert "more or less fragile" in rep.lower() or "fragile" in rep.lower()


def test_g2_reference_matches_assignment():
    r = _res()
    g2b = r["reference_G2"]["baseline"]
    assert abs(g2b["mean5y"] - 5.410) < 1e-9
    assert abs(r["reference_G2"]["configs"]["S1"]["mean5y"] - 4.571) < 1e-9
    assert abs(r["reference_G2"]["configs"]["S3"]["mean5y"] - 4.578) < 1e-9
    # oc_carryfric G2+carry f=0.25 values quoted in the assignment
    assert abs(r["carry_f025"]["G2"]["S1"]["R_5y"] - 4.696) < 1e-9
    assert abs(r["carry_f025"]["G2"]["S3"]["R_5y"] - 4.717) < 1e-9
    assert r["checks"]["g2carry_recompute_max_gap"] == 0.0


def test_g2k20_carry_passes_where_g2_fails():
    r = _res()
    # G2K20 without carry (assignment context)
    assert abs(r["configs"]["S1"]["mean5y"] - 4.903) < 0.02
    assert abs(r["configs"]["S3"]["mean5y"] - 4.924) < 0.02
    # G2K20 + carry f=0.25 keeps 5y >= 5.0 and DD < 20 under every G2-failing friction
    for s in ("S1", "S3", "S4", "S5"):
        c = r["carry_f025"]["G2K20"][s]
        assert c["R_5y"] >= 5.0, s
        assert max(c["DD_maxyearly"], c["full_path_dd_chained"]) < 20, s
    assert abs(r["carry_f025"]["G2K20"]["S1"]["R_5y"] - 5.022) < 0.02
    assert abs(r["carry_f025"]["G2K20"]["S3"]["R_5y"] - 5.056) < 0.02


def test_fold_note_and_robust_report():
    r = _res()
    fold = r["most_recent_year_fold"]["fold_4_most_recent_year"]
    assert fold["good"] is False
    assert abs(fold["test"]["R"] - 4.716) < 1e-9
    assert r["most_recent_year_fold"]["transfer"] is False
    rep = (D / "ROBUST.md").read_text()
    assert "FAILED the most-recent-year fold" in rep
    assert "4.716 vs 5.06" in rep
    assert "Plain YES" in rep
    assert "UNCHANGED" in rep
