"""Tests for oc_gapstress: gap-stress reporting integrity for R2B1D17BF.

Fast checks only (no simulation): file presence/ordering, input-data cut,
reconstruction quality flags, loss-math consistency (caps monotonic, singles
bounded by all-coin, shares in range), JSON/REPORT consistency.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_gapstress"
KPI = ROOT / "research/tournament" / "oc_kpi"
CUT = pd.Timestamp("2026-09-24", tz="UTC")


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "compute_gapstress.py", "results.json", "REPORT.md"):
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


def test_dist_ordering_and_bounds():
    r = _res()
    scopes = [r["phases"][s] for s in ("0", "1", "2", "3")] + [r["mix"]]
    for o in scopes:
        for key, d in o["gaps"].items():
            assert d["n"] > 1000
            assert d["median"] <= d["p99"] <= d["max"]
        for coin, d in o["single_m10"].items():
            assert d["median"] <= d["p99"] <= d["max"]
        for cap, sh in o["shares_m10"].items():
            for k in ("gt20", "gt50", "gt20_of_live", "gt50_of_live"):
                assert 0.0 <= sh[k] <= 1.0
            assert sh["gt50"] <= sh["gt20"]
        assert 0.0 < o["coverage"] <= 1.0


def test_caps_monotonic_and_singles_bounded():
    r = _res()
    scopes = [r["phases"][s] for s in ("0", "1", "2", "3")] + [r["mix"]]
    for o in scopes:
        for g in ("m5", "m10", "m20"):
            u = o["gaps"][f"all_{g}_uncapped"]["max"]
            c3 = o["gaps"][f"all_{g}_cap3"]["max"]
            c2 = o["gaps"][f"all_{g}_cap2"]["max"]
            assert c2 <= c3 <= u
            assert o["gaps"][f"all_{g}_uncapped"]["median"] == o["gaps"][f"all_{g}_cap2"]["median"]
        amax = o["gaps"]["all_m10_uncapped"]["max"]
        for coin, d in o["single_m10"].items():
            assert d["max"] <= amax


def test_worst10_consistent_with_dist():
    r = _res()
    scopes = [r["phases"][s] for s in ("0", "1", "2", "3")] + [r["mix"]]
    for o in scopes:
        w = o["worst10_all_m10_uncapped"]
        assert len(w) == 10
        losses = [x["loss_pct"] for x in w]
        assert losses == sorted(losses, reverse=True)
        assert abs(losses[0] - o["gaps"]["all_m10_uncapped"]["max"]) < 0.05
        for x in w:
            assert pd.Timestamp(x["t"], tz="UTC") < CUT
            assert x["gross"] >= x["dip_gross"] and x["gross"] >= x["book_gross"]


def test_loss_math_spot_check():
    # DOWN gap: long-only 2x gross must lose ~20% at -10% (+taker on ~1.8 notional)
    S, G, g, taker = 2.0, 2.0, 0.10, 0.00055
    expect = 100.0 * (S * g + taker * G * (1 - g))
    assert abs(expect - 20.099) < 1e-9
    r = _res()
    assert r["taker"] == taker
    # peak minute sanity: mix worst gross ~5.8 -> loss ~58%
    top = r["mix"]["worst10_all_m10_uncapped"][0]
    assert abs(top["loss_pct"] - 100 * (top["gross"] * 0.10) - 100 * taker * top["gross"] * 0.9) < 2.0


def test_report_consistent():
    rep = (W / "REPORT.md").read_text()
    r = _res()
    assert "R2B1D17BF" in rep
    assert f"{r['mix']['gaps']['all_m10_uncapped']['max']:.1f}" in rep
    for s in ("0", "1", "2", "3"):
        assert f"{r['phases'][s]['gaps']['all_m10_uncapped']['max']:.1f}" in rep
