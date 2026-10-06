"""Tests for oc_capscale (light: helpers always; results integrity when present)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "diagnostics" / "oc_capscale"


def _mod():
    spec = importlib.util.spec_from_file_location("run_oc_capscale", D / "run_oc_capscale.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_files_exist():
    assert (D / "PLAN.md").exists()
    assert (D / "run_oc_capscale.py").exists()


def test_placeable_floor_logic():
    m = _mod()
    btc = {"minQty": 0.001, "qtyStep": 0.001, "minNotional": 5.0}
    # exactly one step at 60k BTC = 60 USDT -> placeable
    assert m.placeable(0.001, 60000.0, btc) is True
    # below one step -> floored to zero -> skipped
    assert m.placeable(0.0009, 60000.0, btc) is False
    # tiny notional on XRP steps (0.1 XRP ~ 0.3 USDT) -> skipped
    xrp = {"minQty": 0.1, "qtyStep": 0.1, "minNotional": 5.0}
    assert m.placeable(1.0, 3.0, xrp) is False
    assert m.placeable(10.0, 3.0, xrp) is True


def test_geo_mean_monthly():
    m = _mod()
    assert abs(m.geo_mean_monthly([5.0] * 5) - 5.0) < 1e-9
    assert abs(m.geo_mean_monthly([0.0] * 5)) < 1e-9
    # v421 R2B1D17BFG2 years -> 5.41
    yrs = [2.588, 3.282, 6.045, 10.677, 4.648]
    assert abs(m.geo_mean_monthly(yrs) - 5.41) < 0.01


def test_bar_positions_and_pairing():
    m = _mod()
    idx = pd.DatetimeIndex([pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(hours=4 * i)
                            for i in range(5)])
    ts = pd.to_datetime(["2021-09-24T08:00:00Z", "2021-09-24T12:30:00Z"], utc=True)
    pos = m.bar_positions(idx, ts)
    assert list(pos) == [1, 2]
    ev = [dict(kind="rung_fill", weight=0.04, price=60000.0, t="x", symbol="BTCUSDT"),
          dict(kind="rung_tp", ret=0.02, t="y"),
          dict(kind="order_issue", weight=0.1),
          dict(kind="rung_fill", weight=0.03, price=3000.0, t="z", symbol="ETHUSDT"),
          dict(kind="rung_sl", ret=-0.03, t="w")]
    pairs = m.pair_rung_losses(ev)
    assert len(pairs) == 2
    assert pairs[0][1] == 0.02 and pairs[1][1] == -0.03


def _res():
    p = D / "results.json"
    if not p.exists():
        pytest.skip("results.json not produced yet")
    return json.loads(p.read_text())


def test_plan_predates_results():
    if not (D / "results.json").exists():
        pytest.skip("results.json not produced yet")
    assert (D / "PLAN.md").stat().st_mtime <= (D / "results.json").stat().st_mtime


def test_unconstrained_matches_v421():
    r = _res()
    u = r["unconstrained"]
    assert abs(u["R5"] - 5.41) < 0.02
    assert abs(u["W"] - 2.588) < 0.02
    assert abs(u["maxDD"] - 16.91) < 0.05
    assert abs(u["fullDD"] - 16.82) < 0.05


def test_rows_integrity_and_deltas():
    r = _res()
    assert set(r["rows"]) == {"2000", "5000", "10000", "25000"}
    prev = -1e9
    for a in ("2000", "5000", "10000", "25000"):
        d = r["rows"][a]
        assert d["R5"] >= prev - 1e-9  # larger accounts do no worse
        prev = d["R5"]
        for k in ("book_skip", "dip_share", "book_bybit_share"):
            assert 0.0 <= d[k] <= 1.0
        assert d["maxDD"] >= 0 and d["fullDD"] >= 0
        assert abs(d["dR5"] - (d["R5"] - r["unconstrained"]["R5"])) < 1e-9
        assert len(d["years_R"]) == 5 and len(d["years_DD"]) == 5
        assert set(d["by_coin"]) <= {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}


def test_report_verdict():
    if not (D / "REPORT.md").exists():
        pytest.skip("REPORT.md not produced yet")
    rep = (D / "REPORT.md").read_text()
    assert "VERDICT" in rep or "Khuy" in rep
