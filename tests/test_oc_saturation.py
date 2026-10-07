"""Tests for oc_saturation: diagnostic integrity of the dip-size saturation study.

Fast checks only (no simulation, no 1m data): file presence, G2K20 replica
match flags, results.json internal consistency against stored sources, and unit
tests of the sweep/cut helpers on synthetic frames.
"""
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAT = ROOT / "research/diagnostics/oc_saturation"
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load_sat():
    spec = importlib.util.spec_from_file_location("oc_saturation", SAT / "oc_saturation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((SAT / "results.json").read_text())


def test_files_present():
    for f in ("run_g2k20.py", "oc_saturation.py", "REPORT.md", "results.json"):
        assert (SAT / f).exists(), f
    for s in range(4):
        for pat in ("events_g2k20_s{}.parquet", "rungs_g2k20_s{}.parquet",
                    "attrib_g2k20_s{}.parquet", "bars_g2k20_s{}.parquet",
                    "check_g2k20_s{}.json"):
            assert (SAT / pat.format(s)).exists(), pat.format(s)


def test_g2k20_replica_match_1e9():
    for s in range(4):
        c = json.loads((SAT / f"check_g2k20_s{s}.json").read_text())
        assert c["match_1e9"] and c["max_rel_diff"] <= 1e-9
        assert c["overlap"] == c["ref_bars"] == 10944
        assert c["unpaired_exits"] == 0 and c["n_rungs"] > 4000


def test_ladder_matches_sources():
    r = _res()["ladder"]
    v411 = json.loads((RD / "v411" / "v411_result.json").read_text())["rows"]["R2B1D17BF"]
    v422 = json.loads((RD / "v422" / "v422_result.json").read_text())["rows"]["G2K20"]
    v407 = json.loads((RD / "v407" / "v407_result.json").read_text())["rows"]["R2B1D20"]
    assert abs(r["D17BF"]["R"] - v411["R"]) < 1e-9
    assert abs(r["G2K20"]["R"] - v422["R"]) < 1e-9
    assert abs(r["D20"]["R"] - v407["R"]) < 1e-9
    assert r["G2K20"]["kd"] == 2.0 and r["G2K20"]["G"] == 2.0 and r["G2K20"]["budget"] == 0.52
    assert r["D17BF"]["kd"] == 1.7 and r["D17BF"]["G"] is None
    # saturation ordering: top rows within 0.05 R, DD wall separates them
    assert abs(r["G2K20"]["R"] - 5.874) < 1e-9
    assert r["D20"]["DD"] > 20 >= r["G2K20"]["DD"]


def test_depth_tables_reconcile():
    r = _res()["rows"]
    for name in ("D17BF", "G2K20"):
        row = r[name]
        n_sum = sum(v["n"] for v in row["by_depth"].values())
        assert n_sum == row["n_rungs"] == sum(v["n"] for v in row["by_year"].values())
        pnl_sum = sum(v["pnl"] for v in row["by_depth"].values())
        assert abs(pnl_sum - row["total_pnl"]) < 0.05
        assert 0.0 <= row["B1_cut_share"] <= 0.6 and 0.0 <= row["B1_hit_share"] <= 1.0
        # deeper rungs earn more per unit than shallow ones (both rows)
        assert row["by_depth"]["5.0"]["per_unit"] > row["by_depth"]["2.5"]["per_unit"]


def test_kd_invariance_and_cap():
    r = _res()["rows"]
    # per-unit edge survives the kd 1.7 -> 2.0 step (mechanical, not economic, saturation)
    assert abs(r["D17BF"]["pooled_per_unit"] - r["G2K20"]["pooled_per_unit"]) < 0.001
    for depth in ("2.5", "3.0", "3.5", "4.0", "5.0"):
        a, b = r["D17BF"]["by_depth"][depth]["per_unit"], r["G2K20"]["by_depth"][depth]["per_unit"]
        assert abs(a - b) < 0.002, depth
    # the cap truncates the tail and skips ~1% of fills
    assert r["G2K20"]["cap_counterfactual"]["max_concurrent"] <= 2.0 + 1e-9
    assert r["D17BF"]["cap_counterfactual"]["max_concurrent"] > 2.0
    assert r["G2K20"]["n_rungs"] < r["D17BF"]["n_rungs"]
    # cascade: late fills earn less than half of early fills at both sizes
    for name in ("D17BF", "G2K20"):
        c = r[name]["cascade"]
        assert c["late"]["per_unit"] < 0.5 * c["early"]["per_unit"]
    # marginals arithmetic
    m = _res()["marginals"]
    assert abs((_res()["ladder"]["G2K20"]["R"] - _res()["ladder"]["D17BF"]["R"]) - 0.449) < 1e-9
    assert m["D17BF_to_G2_cap_at_1.7"]["dDD"] == -1.42


def test_report_has_vietnamese_conclusion():
    rep = (SAT / "REPORT.md").read_text(encoding="utf-8")
    assert "Ket luan" in rep and "saturation is MECHANICAL" in rep.upper() or "MECHANICAL" in rep


def test_helpers_on_synthetic():
    mod = _load_sat()
    R = pd.DataFrame([
        dict(fill_t=pd.Timestamp("2022-01-01 00:16", tz="UTC"), exit_t=pd.Timestamp("2022-01-01 01:00", tz="UTC"),
             symbol="BTCUSDT", depth=2.5, exit="rung_tp", weight=0.1, ret=0.01, loss=0.001, shift=0),
        dict(fill_t=pd.Timestamp("2022-01-01 00:20", tz="UTC"), exit_t=pd.Timestamp("2022-01-01 02:00", tz="UTC"),
             symbol="ETHUSDT", depth=5.0, exit="rung_sl", weight=0.2, ret=-0.02, loss=-0.004, shift=0),
    ])
    y = mod.year_of(R["exit_t"])
    assert list(y.astype(str)) == ["21", "21"]
    cs = mod.cap_stats(R, G=2.0)
    assert cs["fills_total"] == 2 and cs["max_concurrent"] == 0.3
    assert cs["fills_near_cap"] == 0
    cs2 = mod.cap_stats(R, G=0.15)
    assert cs2["fills_near_cap"] == 1 and cs2["fill_share"] == 0.5
