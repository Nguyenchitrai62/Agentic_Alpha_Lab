"""Tests for oc_margin: Bybit cross-margin report integrity for R2B1D17BFG2.

Fast checks only (no simulation): file presence/ordering, input-data cut,
reconstruction quality flags, margin-math consistency, JSON/REPORT consistency.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_margin"
KPI = ROOT / "research/tournament" / "oc_kpi_g2"
CUT = pd.Timestamp("2026-09-24", tz="UTC")
MMR, TAKER = 0.005, 0.00055


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "compute_margin.py", "results.json", "REPORT.md"):
        assert (W / f).exists(), f


def test_plan_predates_results():
    assert (W / "PLAN.md").stat().st_mtime <= (W / "results.json").stat().st_mtime


def test_no_data_at_or_after_cut():
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(ev["t"], utc=True).max() < CUT
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(bs["t"], utc=True).max() < CUT
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t"])
    assert pd.to_datetime(h["t"], utc=True).max() < CUT + pd.Timedelta(days=1)


def test_reconstruction_quality():
    r = _res()
    for s in ("0", "1", "2", "3"):
        o = r["phases"][s]
        rc = o["recon_vs_barsum"]
        assert rc["median_abs_diff"] <= 0.005
        assert rc["max_abs_diff"] <= 0.3
        assert rc["n_bars"] == 10943
        bi = o["build_info"]
        assert bi["fills_from_open"] == 0
        assert bi["reduce_overrun_max"] == 0.0
        assert bi["unpaired_rung_exits"] == 0


def test_margin_math_spot_check():
    # Bybit IM = G/L; d_liq = (1-MMR*G)/(G*(1-MMR)); gap loss formula.
    G, L, g = 3.4113, 5, 0.10
    assert abs(G / L - 0.68226) < 1e-4
    d = (1 - MMR * G) / (G * (1 - MMR))
    assert abs(d - 0.2896) < 1e-3
    S = 3.38
    expect = 100.0 * (S * g + TAKER * G * (1 - g))
    assert abs(expect - 33.969) < 0.01
    r = _res()
    assert r["MMR"] == MMR and r["taker"] == TAKER
    m = r["mix"]
    assert abs(m["G_max"] / 5 - m["leverage"]["5"]["max_IM"]) < 1e-3
    assert m["min_leverage_never_blocked"] == 5
    assert m["leverage"]["3"]["n_blocked_samples"] > 0
    assert m["leverage"]["5"]["n_blocked_samples"] == 0


def test_leverage_ordering_and_bounds():
    r = _res()
    scopes = [r["phases"][s] for s in ("0", "1", "2", "3")] + [r["mix"]]
    for o in scopes:
        assert o["G_median"] <= o["G_p99"] <= o["G_max"]
        im3 = o["leverage"]["3"]["max_IM"]
        im5 = o["leverage"]["5"]["max_IM"]
        im10 = o["leverage"]["10"]["max_IM"]
        im20 = o["leverage"]["20"]["max_IM"]
        assert im20 <= im10 <= im5 <= im3
        assert o["leverage"]["5"]["share_blocked_open"] == 0.0
        a = o["at_min_leverage"]
        assert a["L"] == o["min_leverage_never_blocked"] == 5
        assert a["free_min"] <= a["free_p1"] <= a["free_median"]
        assert a["dliq_min"] <= a["dliq_p1"] <= a["dliq_median"]
        assert 0.0 < o["coverage"] <= 1.0
        for gk, gd in o["gaps"].items():
            assert 0.0 <= gd["share_liquidated_open"] <= 1.0
            assert gd["loss_median"] <= gd["loss_p99"] <= gd["loss_max"]


def test_worst10_consistent_with_dist():
    r = _res()
    scopes = [r["phases"][s] for s in ("0", "1", "2", "3")] + [r["mix"]]
    for o in scopes:
        w = o["worst10_m10"]
        assert len(w) == 10
        losses = [x["loss_pct"] for x in w]
        assert losses == sorted(losses, reverse=True)
        assert abs(losses[0] - o["gaps"]["m10"]["loss_max"]) < 0.05
        for x in w:
            assert pd.Timestamp(x["t"], tz="UTC") < CUT
            assert x["gross"] >= x["dip_gross"] and x["gross"] >= x["book_gross"]
            assert x["liquidated"] is False


def test_report_consistent():
    rep = (W / "REPORT.md").read_text(encoding="utf-8")
    r = _res()
    assert "R2B1D17BFG2" in rep
    assert "5x" in rep
    assert f"{r['mix']['G_max']:.3f}" in rep
    assert f"{100 * r['mix']['at_min_leverage']['dliq_min']:.1f}" in rep
    for s in ("0", "1", "2", "3"):
        assert f"{r['phases'][s]['G_max']:.3f}" in rep
