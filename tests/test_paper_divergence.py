"""Tests for scripts/paper_divergence.py. Synthetic fixtures only, no network."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import paper_divergence as pdv  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _iso(t):
    return t.isoformat()


def _write_bot(d: Path, eq_pts, execs=(), links=()):
    d.mkdir(parents=True, exist_ok=True)
    (d / "exchange.json").write_text(
        __import__("json").dumps({"equity_curve": [[_iso(t), v] for t, v in eq_pts],
                                            "execs": list(execs), "orders": {}}), encoding="utf-8")
    (d / "state.json").write_text(
        __import__("json").dumps({"links": {l: {"order": {"kind": "entry", "piece": p, "symbol": s,
                                                           "meta": {"kind": k}}}
                                             for l, p, s, k in links}}), encoding="utf-8")


def _write_plan(p: Path, eq_pts, fills=()):
    import json
    p.write_text(json.dumps({"equity_curve": [[_iso(t), v] for t, v in eq_pts],
                             "events": [{"kind": "book_fill", "t": _iso(t), "symbol": s}
                                        for t, s in fills]}), encoding="utf-8")


def test_divergence_math_and_monthly_annualisation(tmp_path):
    # bot +0.5% over 15 days, plan +0.2% over the same window -> div 0.3pp
    bpts = [(T0, 5000.0), (T0 + timedelta(days=15), 5025.0)]
    ppts = [(T0 - timedelta(days=1), 0.99), (T0, 1.0),
            (T0 + timedelta(days=15), 1.002)]
    _write_bot(tmp_path / "paper", bpts)
    pj = tmp_path / "plan.json"
    _write_plan(pj, ppts)
    plan = pdv.load_plan(str(pj))
    r = pdv.summarize(str(tmp_path / "paper"), plan)
    assert r["bot_return_pct"] == round(100 * (5025 / 5000 - 1), 4)
    assert r["plan_return_pct"] == round(100 * (1.002 / 1.0 - 1), 4)
    assert r["div_pp"] == round(0.5 - 0.2, 4)
    assert r["div_pp_per_month"] == pytest.approx(0.3 * pdv.DAYS_PER_MONTH / 15, abs=1e-3)
    assert r["verdict"] == "PASS"  # 15d >= 14d, |div| <= 1.5
    assert r["config"].startswith("same-config")


def test_verdict_fail_and_too_early(tmp_path):
    _write_bot(tmp_path / "paper", [(T0, 5000.0), (T0 + timedelta(days=20), 5100.0)])  # +2%
    pj = tmp_path / "plan.json"
    _write_plan(pj, [(T0, 1.0), (T0 + timedelta(days=20), 1.0)])  # flat
    plan = pdv.load_plan(str(pj))
    r = pdv.summarize(str(tmp_path / "paper"), plan)
    assert r["div_pp_per_month"] == pytest.approx(2.0 * pdv.DAYS_PER_MONTH / 20, abs=1e-3)  # ~3.04
    assert r["verdict"] == "FAIL"
    _write_bot(tmp_path / "paper2", [(T0, 5000.0), (T0 + timedelta(days=2), 5100.0)])
    r2 = pdv.summarize(str(tmp_path / "paper2"), plan)
    assert r2["verdict"] == "too early"  # < 14 days regardless of size


def test_no_plan_path_label_for_other_configs(tmp_path):
    _write_bot(tmp_path / "paper_d17bf", [(T0, 5000.0), (T0 + timedelta(days=2), 5001.0)])
    pj = tmp_path / "plan.json"
    _write_plan(pj, [(T0, 1.0), (T0 + timedelta(days=2), 1.0)])
    plan = pdv.load_plan(str(pj))
    r = pdv.summarize(str(tmp_path / "paper_d17bf"), plan)
    assert r["config"].startswith("no plan path")
    assert "closest" in r["config"] and "closest" in r["plan"]
    assert r["verdict"] == "too early"


def test_fill_reconciliation_counts(tmp_path):
    t1 = T0 + timedelta(hours=5)
    ms = lambda t: str(int(t.timestamp() * 1000))
    execs = [{"orderLinkId": "b0ETHxE", "execQty": "0.02", "execPrice": "2700",
              "execTime": ms(t1)},
             {"orderLinkId": "d0BTCxE", "execQty": "0.001", "execPrice": "85000",
              "execTime": ms(t1)}]
    links = [("b0ETHxE", "b0ETHx", "ETHUSDT", "book"),
             ("d0BTCxE", "d0BTCx", "BTCUSDT", "dip")]
    _write_bot(tmp_path / "paper", [(T0, 5000.0), (t1, 5000.0)], execs, links)
    pj = tmp_path / "plan.json"
    _write_plan(pj, [(T0, 1.0), (t1, 1.0)],
                fills=[(t1, "ETHUSDT"), (t1, "SOLUSDT")])
    plan = pdv.load_plan(str(pj))
    r = pdv.summarize(str(tmp_path / "paper"), plan)
    assert r["bot_entry_fills"] == 2 and r["plan_book_fills"] == 2
    assert r["per_symbol"]["ETHUSDT"]["matched"] == 1
    assert r["fills_only_in_bot"] == 1  # BTC dip entry
    assert r["fills_only_in_plan"] == 1  # SOL plan fill


def test_no_overlap_and_missing_curve(tmp_path):
    _write_bot(tmp_path / "paper", [(T0, 5000.0), (T0 + timedelta(days=1), 5001.0)])
    pj = tmp_path / "plan.json"
    _write_plan(pj, [(T0 + timedelta(days=10), 1.0), (T0 + timedelta(days=11), 1.0)])
    plan = pdv.load_plan(str(pj))
    r = pdv.summarize(str(tmp_path / "paper"), plan)
    assert r["verdict"] == "too early"  # single anchor point -> no comparison
    assert "status" in r
    r2 = pdv.summarize(str(tmp_path / "absent"), plan)
    assert r2["verdict"] == "too early" and "status" in r2


def test_plan_window_ffill_anchor():
    curve = [(T0 - timedelta(hours=5), 0.9), (T0 - timedelta(hours=1), 1.0),
             (T0 + timedelta(hours=1), 1.1)]
    seg = pdv.plan_window(curve, T0, T0 + timedelta(hours=1))
    assert [v for _, v in seg] == [1.0, 1.1]  # ffill anchor, not 0.9
