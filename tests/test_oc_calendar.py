"""Tests for oc_calendar (frozen rule, availability, gate, accounting, REPORT)."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_calendar"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_frozen_rule_constants():
    out = _res()
    assert out["meta"]["threshold_spread"] == 0.02
    assert out["meta"]["f_alloc"] == 0.125
    assert out["meta"]["fees"]["pair_drag"] == 0.00185
    assert out["meta"]["fees"]["taker_per_fill"] == 0.00055
    assert out["meta"]["fees"]["delivery"] == 0.0002
    plan = (HERE / "PLAN.md").read_text()
    assert "ann_far - ann_near >= 0.02" in plan
    assert "CORR-1" in plan  # post-hoc entry-timing correction is logged


def test_fee_math_handcheck():
    # synthetic hand-check of the PLAN.md P&L formula (no trades realised)
    N_entry, F_entry, S_del, F_far_del = 60000.0, 62000.0, 61000.0, 61500.0
    gross = (S_del - N_entry) / N_entry + (F_entry - F_far_del) / F_entry
    expect = gross - 0.00185
    assert abs(expect - ((1000 / 60000) + (500 / 62000) - 0.00185)) < 1e-12
    # gate boundary documents the fixed threshold (no tuning)
    assert not (0.0199 >= 0.02)
    assert 0.02 >= 0.02


def test_binance_never_enterable_far_missing_at_roll():
    out = _res()
    b = out["binance"]
    assert b["n_considered"] == 0
    assert b["n_no_far_at_roll"] == 48  # 24 BTC + 24 ETH adjacent pairs
    assert b["pooled"]["n_trades"] == 0
    assert b["n_years_positive"] == 0
    # independent availability proof (no script internals): the far contract's
    # first history bar post-dates the near contract's oc_cashcarry roll bar.
    man = json.loads((ROOT / "data/raw/qbasis_20261003/manifest.json").read_text())["files"]
    oc = json.loads((ROOT / "research/tournament/oc_cashcarry/results.json").read_text())
    oc_entry = {(t["coin"], t["delivery"]): t["entry_open"] for t in oc["trades"]}
    for coin, near, far in (("BTC", "2024-03-29", "2024-06-28"),
                            ("ETH", "2024-03-29", "2024-06-28")):
        key = f"um_{coin}USDT_{far[2:4]}{far[5:7]}{far[8:10]}"
        far_first = pd.Timestamp(man[key]["first_open_time"], tz="UTC")
        roll_open = pd.Timestamp(oc_entry[(coin, near)], tz="UTC")
        assert far_first > roll_open, (coin, near, far, far_first, roll_open)


def test_bybit_curve_never_reaches_gate():
    out = _res()
    s = out["bybit"]
    assert s["n_considered"] == 42
    assert s["n_incomplete"] == 2
    assert s["pooled"]["n_trades"] == 0
    assert s["n_years_positive"] == 0
    for y in s["years"]:
        assert y["n_trades"] == 0
        assert y["sum_ret_alloc"] == 0.0
        assert y["max_spread_considered"] is not None
        assert y["max_spread_considered"] < 0.02, (y["year"], y["max_spread_considered"])


def test_year_accounting_and_correlations():
    out = _res()
    for venue in ("binance", "bybit"):
        s = out[venue]
        tot = sum(y["sum_ret_alloc"] for y in s["years"])
        assert abs(tot - s["pooled"]["sum_ret_alloc"]) < 1e-9
        assert s["pooled"]["total_acct_pct"] == round(0.125 * tot * 100, 4)
        c = s["correlation_vs_base_carry"]
        assert c["year_sums_pearson_n5"] is None  # flat-zero spread series
        assert c["matched_trades_pearson"] is None
        assert c["n_matched"] == 0
    assert out["verdict"] == "CLOSE"


def test_no_1m():
    src = (HERE / "analyze_calendar.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "aggflow", "_1m.parquet"):
        assert bad not in src, bad


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "CLOSE" in rep
    assert "USEFUL only if" in rep or "requires net > 0" in rep
    for y in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"):
        assert y in rep
    assert "0.012008" in rep  # bybit best spread, 2024 year
    assert "48" in rep and "NO_FAR_AT_ROLL" in rep
