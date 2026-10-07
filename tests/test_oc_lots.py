"""Tests for oc_lots (light: no simulation, checks results.json + PLAN ordering)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_lots"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ACCTS = ("1000.0", "2000.0", "5000.0", "10000.0", "20000.0")


def _res():
    return json.loads((D / "results.json").read_text())


def test_files_exist():
    assert (D / "PLAN.md").exists()
    assert (D / "run_oc_lots.py").exists()
    assert (D / "results.json").exists()
    assert (D / "REPORT.md").exists()


def test_plan_predates_results():
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_inputs_and_lots():
    r = _res()
    assert r["variant"] == "R2B1D17BF" and r["phase"] == 0
    assert r["inputs"]["n_book_orders"] == 2325
    assert r["inputs"]["n_book_fills"] == 1312
    assert r["inputs"]["n_rungs"] == 5466
    exp_min = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1, "BNBUSDT": 0.01, "XRPUSDT": 0.1}
    for s in SYMS:
        assert r["lot_rules"][s]["minQty"] == exp_min[s]
        assert r["lot_rules"][s]["minNotional"] == 5.0


def test_shares_monotone_and_top():
    r = _res()
    prev_b = prev_r = -1.0
    for a in ACCTS:
        d = r["per_account"][a]
        assert d["book_share"] >= prev_b - 1e-9
        assert d["rung_share"] >= prev_r - 1e-9
        prev_b, prev_r = d["book_share"], d["rung_share"]
        assert set(d["by_coin"]) == set(SYMS)
        assert sum(c["book_n"] for c in d["by_coin"].values()) == d["book_orders"]
        assert sum(c["rung_n"] for c in d["by_coin"].values()) == d["rung_orders"]
        for k in ("dip_gross_share", "book_gross_share", "dip_notional_share", "book_notional_share"):
            assert 0.0 <= d[k] <= 1.0005
    top = r["per_account"]["20000.0"]
    assert top["book_share"] == 1.0
    assert top["rung_share"] >= 0.99


def test_btc_is_bottleneck_at_1000():
    r = _res()
    d = r["per_account"]["1000.0"]["by_coin"]
    assert d["BTCUSDT"]["book_share"] < d["BNBUSDT"]["book_share"]
    assert d["BTCUSDT"]["rung_share"] < d["XRPUSDT"]["rung_share"]
    assert len(r["per_anchor_year"]) == 5


def test_report_verdict():
    rep = (D / "REPORT.md").read_text()
    assert "VERDICT" in rep
