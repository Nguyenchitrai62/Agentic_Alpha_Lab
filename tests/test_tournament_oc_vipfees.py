"""Tests for oc_vipfees: VIP fee-repricing reporting integrity for R2B1D17BFG2.

Fast checks only (no simulation): file presence/ordering, input-data cut,
fee-math consistency (non-negative savings, VIP2 >= VIP1, compounding
identity, turnover/volume identity), JSON/REPORT consistency.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "research/tournament/oc_vipfees"
G2 = ROOT / "research/tournament/oc_kpi_g2"
CUT = pd.Timestamp("2026-09-24", tz="UTC")


def _res():
    return json.loads((W / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "compute_vipfees.py", "results.json", "REPORT.md"):
        assert (W / f).exists(), f


def test_plan_predates_results():
    assert (W / "PLAN.md").stat().st_mtime <= (W / "results.json").stat().st_mtime


def test_no_data_at_or_after_cut():
    for s in range(4):
        ev = pd.read_parquet(G2 / f"events_s{s}.parquet", columns=["t"])
        assert pd.to_datetime(ev["t"], utc=True).max() < CUT


def test_schedules_and_thresholds():
    r = _res()
    assert r["fee_schedules"]["VIP0"] == {"maker": 0.0002, "taker": 0.00055}
    assert r["fee_schedules"]["VIP1"] == {"maker": 0.00018, "taker": 0.0004}
    assert r["fee_schedules"]["VIP2"] == {"maker": 0.00016, "taker": 0.000375}
    assert r["tier_volume_threshold_30d_usdt"] == {"VIP1": 10_000_000.0, "VIP2": 25_000_000.0}
    assert "ASSUMED" in r["fee_schedule_note"]


def test_savings_nonneg_and_ordered():
    r = _res()
    ms = r["monthly_saving_pct"]
    assert len(ms) == 61
    assert r["checks"]["all_monthly_savings_nonneg"]
    for m, d in ms.items():
        assert d["VIP2"] >= d["VIP1"] >= 0.0, m
    f = r["five_year"]
    assert f["net_VIP2_pct"] >= f["net_VIP1_pct"] >= f["net_old_pct"]
    assert f["gain_VIP2_pp_per_month"] >= f["gain_VIP1_pp_per_month"] > 0
    for y in r["per_anchor_year"]:
        assert y["gain_VIP2_pp"] >= y["gain_VIP1_pp"] > 0


def test_compounding_identity():
    r = _res()
    eq = json.loads((G2 / "results_equity.json").read_text())
    old = {m: v / 100 for m, v in eq["monthly"]}
    ms = r["monthly_saving_pct"]
    for tier in ("VIP1", "VIP2"):
        p = 1.0
        for m, v in eq["monthly"]:
            p *= 1 + v / 100 + ms[m][tier] / 100
        assert abs(p * 100 - 100 - r["five_year"][f"net_{tier}_pct"]) < 0.05, tier
    # net_old from the same rounded monthlies (oc_kpi_g2 exact net is 2538.74;
    # +0.47pp residual is the 2dp-monthly rounding, identical for all tiers)
    p = 1.0
    for _, v in eq["monthly"]:
        p *= 1 + v / 100
    assert abs(p * 100 - 100 - r["five_year"]["net_old_pct"]) < 0.01
    assert abs(r["five_year"]["net_old_pct"] - 2538.74) < 1.0


def test_turnover_volume_identity():
    r = _res()
    tau = r["turnover_per_month"]
    assert 1.0 < tau < 200.0
    for e in ("5000", "10000", "50000"):
        assert r["volume_at_equity_usdt"][e]["monthly_volume_usdt"] == round(tau * float(e), 0)
    assert r["equity_required_usdt"]["VIP1"] == round(10_000_000.0 / tau, 0)
    assert r["equity_required_usdt"]["VIP2"] == round(25_000_000.0 / tau, 0)
    assert r["equity_required_usdt"]["VIP2"] > r["equity_required_usdt"]["VIP1"]


def test_flip_counts_bounded():
    r = _res()
    fl = r["sign_flips"]
    assert fl["VIP1"]["rung_n"] == 21513 and fl["VIP2"]["rung_n"] == 21513
    assert fl["VIP1"]["book_n"] == 5064 and fl["VIP2"]["book_n"] == 5064
    assert fl["VIP1"]["rung"] <= fl["VIP2"]["rung"]
    assert fl["VIP1"]["book"] <= fl["VIP2"]["book"]
    assert fl["VIP2"]["rung"] / 21513 < 0.02
    assert fl["VIP2"]["book"] / 5064 < 0.01


def test_report_consistency():
    r = _res()
    rep = (W / "REPORT.md").read_text()
    f = r["five_year"]
    assert str(round(f["gain_VIP1_pp_per_month"], 4)) in rep
    assert str(round(f["gain_VIP2_pp_per_month"], 4)) in rep
    assert "435k" in rep and "1.09M" in rep
    assert "2539" in rep and "2712" in rep and "2789" in rep
    assert "no verdict" in rep.lower() or "no selection rule" in rep
