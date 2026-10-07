"""Tests for oc_utamargin2: POST-HOC carry-short leverage sensitivity.

Fast checks only (no rebuild): file presence, cut discipline, 5x
reproduction of oc_utamargin, per-cell margin-math consistency, haircut
monotonicity, verdict cells, squeeze isolated-vs-cross logic, venue
leverage evidence, JSON/REPORT consistency, no-1m rule.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_utamargin2"
PREV = ROOT / "research/tournament/oc_utamargin"
CUT = pd.Timestamp("2026-09-24", tz="UTC")
CELLS = [f"f{f}_lev{lev}" for f in (0.25, 0.375, 0.5) for lev in (5, 10, 20)]


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("analyze_utamargin2.py", "results.json", "REPORT.md"):
        assert (W / f).exists(), f


def test_no_data_at_or_after_cut():
    r = _res()
    g0, g1, n = r["meta"]["grid"]
    assert pd.Timestamp(g1, tz="UTC") < CUT
    assert n == 43805
    for k, c in r["cells"].items():
        assert pd.Timestamp(c["worst_hour"], tz="UTC") < CUT, (k, c["worst_hour"])


def test_no_1m():
    src = (W / "analyze_utamargin2.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_post_hoc_labelled():
    r = _res()
    assert r["meta"].get("post_hoc") is True
    assert "0.375" in (W / "REPORT.md").read_text(encoding="utf-8")


def test_single_change_discipline():
    src = (W / "analyze_utamargin2.py").read_text()
    assert "LEV_CARRY_GRID" in src
    assert "short_not / lev" in src  # the one changed IM term
    assert "UNCHANGED" in src  # MM tiers marked unchanged


def test_lev5_reproduces_oc_utamargin():
    r = _res()
    prev = json.loads((PREV / "results.json").read_text())
    for f in ("0.25", "0.5"):
        a = r["cells"][f"f{f}_lev5"]
        b = prev["per_f"][f]
        assert a["n_blocked_hours"] == b["n_blocked_hours"], f
        assert abs(a["max_IM_over_balance"] - b["max_IM_over_balance"]) < 1e-3, f
        assert abs(a["min_free_ratio"] - b["min_free_ratio"]) < 1e-3, f
        assert a["worst_hour"] == b["worst_hour"], f
        assert a["gap10_at_worst"]["loss_pct_of_balance"] == \
            b["gap10_at_worst"]["loss_pct_of_balance"], f


def test_margin_math_consistent():
    r = _res()
    assert sorted(r["cells"]) == sorted(CELLS)
    for k, c in r["cells"].items():
        assert c["n_hours"] == 43805, k
        assert abs(c["min_free_ratio"] - (1 - c["max_IM_over_balance"])) < 1e-3, k
        assert (c["n_blocked_hours"] > 0) == (c["max_IM_over_balance"] > 0.95), k
        assert c["n_mm_breach_hours"] == 0, k
        assert c["max_MM_over_balance"] < 0.05, k
        g = c["gap10_at_worst"]
        assert g["liquidated"] is False, k
        assert 0 < g["loss_pct_of_balance"] < 100, k


def test_haircut_monotonic():
    r = _res()
    for k, c in r["cells"].items():
        h10, h20 = c["haircut_stress"]["0.1"], c["haircut_stress"]["0.2"]
        assert h10["min_free_ratio"] <= c["min_free_ratio"] + 1e-9, k
        assert h20["min_free_ratio"] <= h10["min_free_ratio"] + 1e-9, k
        assert h10["n_blocked_hours"] >= 0 and \
            h20["n_blocked_hours"] >= h10["n_blocked_hours"], k
        for h in (h10, h20):
            assert h["gap10_liquidated_under_stress"] is False, k


def test_verdict_cells():
    r = _res()
    # f=0.375 @10x clears every stress
    v = r["cells"]["f0.375_lev10"]
    assert v["n_blocked_hours"] == 0
    assert v["haircut_stress"]["0.1"]["n_blocked_hours"] == 0
    assert v["haircut_stress"]["0.2"]["n_blocked_hours"] == 0
    # f=0.375 @5x fails the hc10 stress; f=0.5 fails hc20 at every leverage
    assert r["cells"]["f0.375_lev5"]["haircut_stress"]["0.1"]["n_blocked_hours"] >= 1
    for lev in (5, 10, 20):
        assert r["cells"][f"f0.5_lev{lev}"]["haircut_stress"]["0.2"]["n_blocked_hours"] >= 1
    # f=0.25 clears at every leverage (reproduces parent verdict, no borrow)
    for lev in (5, 10, 20):
        c = r["cells"][f"f0.25_lev{lev}"]
        assert c["n_blocked_hours"] == 0
        assert c["haircut_stress"]["0.2"]["n_blocked_hours"] == 0


def test_squeeze_isolated_vs_cross():
    r = _res()
    for k, c in r["cells"].items():
        lev = c["lev_carry"]
        s = c["squeeze30_BTCETH_at_worst"]
        # 30% loss vs notional/lev -> ratio is exactly 0.3*lev
        assert abs(s["isolated_loss_over_IM"] - round(0.3 * lev, 2)) < 1e-9, k
        assert s["isolated_short_survives"] is False, k
        # pooled cross account survives everywhere
        assert s["cross_liquidated"] is False, k
        assert s["cross_blocked"] is False, k
        assert s["account_mode_matters"] is True, k


def test_venue_leverage_evidence():
    r = _res()
    v = r["meta"]["venue_leverage"]
    assert "50.00" in v["linear_dated_BTC_ETH"]["maxLev"]
    inv = v["inverse_dated"]
    assert inv["BTCUSDZ26"] == "100.00"
    assert inv["ETHUSDZ26"] == "50.00"
    assert "ASSUMPTION" in r["meta"]["carry_short_venue_mapping"]
    # 10x/20x within every applicable venue limit
    assert max(r["meta"]["lev_carry_grid"]) * 1.0 < 50.0


def test_report_consistent():
    rep = (W / "REPORT.md").read_text(encoding="utf-8")
    r = _res()
    assert "f = 0.375 at 10x" in rep
    assert "f = 0.50 is NOT cleared" in rep
    assert "ACCOUNT MODE MATTERS" in rep
    assert "100x" in rep and "50x" in rep
    v = r["cells"]["f0.375_lev10"]
    assert f'{v["max_IM_over_balance"] * 100:.2f}' in rep
    assert v["worst_hour"][:10] in rep
