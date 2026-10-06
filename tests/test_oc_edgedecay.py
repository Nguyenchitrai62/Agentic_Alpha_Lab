"""Tests for oc_edgedecay (light, no simulation): file presence, monthly integrity,
trend-stat consistency, half-year cover, component reconciliation, market context,
early-warning thresholds, and the Vietnamese conclusion."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ED = ROOT / "research/diagnostics/oc_edgedecay"
KPI = ROOT / "research/tournament/oc_kpi_g2"
CUT = "2026-09-24"


def _res():
    return json.loads((ED / "results.json").read_text())


def test_files_present():
    for f in ("run_edgedecay.py", "results.json", "REPORT.md"):
        assert (ED / f).exists(), f


def test_monthly_60_and_matches_kpi():
    r = _res()
    assert r["variant"] == "R2B1D17BFG2"
    assert r["trend"]["n_months"] == 60
    assert r["trend"]["months"][0] == "2021-10" and r["trend"]["months"][-1] == "2026-09"
    assert r["trend"]["months"][-1] < CUT[:7] + "-x"  # last month starts before cut
    kpi = json.loads((KPI / "results_equity.json").read_text())["monthly"]
    assert [k for k, _ in kpi[1:]] == r["trend"]["months"]
    assert [v for _, v in kpi[1:]] == [v for _, v in r["monthly_all12"][1:]]
    assert abs(r["checks"]["prod_minus_net"]) < 1e-9


def test_trend_stats_consistent():
    r = _res()["trend"]
    y = np.array([v for _, v in json.loads((ED / "results.json").read_text())["monthly_all12"][1:]], float)
    # monthly_all12 stores rounded values; slope in results uses exact -> allow 1e-2 tolerance
    x = np.arange(60, dtype=float)
    xc = x - x.mean()
    slope = float((xc * (y - y.mean())).sum() / (xc * xc).sum())
    assert abs(slope - r["slope_pp_per_month"]) < 1e-2
    bb = r["block_bootstrap"]
    assert bb["block_months"] == 3 and bb["resamples"] == 5000
    assert bb["ci95_pp_per_month"][0] <= r["slope_pp_per_month"] <= bb["ci95_pp_per_month"][1]
    assert 0 <= bb["p_no_positive_trend"] <= 1
    assert r["first30"]["months"] == ["2021-10", "2024-03"]
    assert r["last30"]["months"] == ["2024-04", "2026-09"]
    d = r["diff_last_minus_first"]
    assert abs(d["mean_pp"] - (r["last30"]["mean"] - r["first30"]["mean"])) < 0.05
    assert d["block_ci95"][0] <= d["mean_pp"] <= d["block_ci95"][1]
    assert r["last6"]["months"] == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    assert len(r["last12"]["months"]) == 12 and r["last12"]["months"][0] == "2025-10"


def test_halves_cover_all_trades():
    r = _res()["components"]
    halves = r["halves"]
    assert len(halves) == 10
    assert sum(h["n_book"] for h in halves) == 5064
    assert sum(h["n_rungs"] for h in halves) == 21513
    for h in halves:
        e = h["rung_sl"] + h["rung_tp"] + h["rung_timeout"]
        assert e == h["n_rungs"]
        for k in ("win_book", "win_rungs", "win_all", "tp_rate", "sl_rate", "timeout_rate"):
            assert h[k] is None or 0 <= h[k] <= 1
        assert 2.0 <= (h["avg_fill_rung"] or 0) <= 5.5
        assert h["half"] < "H9 2026-03-24..2026-09-24x"


def test_component_monthly_reconciles():
    r = _res()["components"]
    assert len(r["monthly"]) == 60
    for c in r["monthly"]:
        assert abs(c["total"] - c["book_pp"] - c["dip_pp"] - c["residual_pp"]) < 0.006
    assert abs(r["book_monthly_mean_pp"] + r["dip_monthly_mean_pp"]
               + r["residual_mean_pp"] - 6.102) < 0.05


def test_market_context_sane():
    m = _res()["market_context"]["halves"]
    assert len(m) == 10
    for h in m:
        assert 10 <= (h["btc_rv_ann_pct"] or 0) <= 150
        fl = h["flushes"]
        assert fl["TOTAL"] == sum(fl[s] for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"))
        assert fl["TOTAL"] > 0


def test_early_warning_and_vietnamese_conclusion():
    r = _res()
    ew = r["early_warning"]
    assert ew["trailing6m_mean_alert_lt"] == 1.61
    assert ew["trailing12m_mean_alert_lt"] == 3.08
    assert ew["half_tp_rate_alert_lt"] == 0.434
    rep = (ED / "REPORT.md").read_text(encoding="utf-8")
    assert "Ket luan" in rep and "VERDICT" in rep
    assert "1.61" in rep and "0.434" in rep
