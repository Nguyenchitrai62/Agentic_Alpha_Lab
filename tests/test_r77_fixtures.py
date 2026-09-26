"""Tests for W2-FIXTURES (R77 items 3+4). RESEARCH ONLY, exploratory labels.

Covers: feed-contract codes, engine-certified semantic fixtures F1..F11,
3 scenarios per fixture, pending/partial restart parity, negative controls
for the verifier stub, unsupported-scenario disclosure. No live orders,
no cloud, no training/fitting/tuning.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)

import copy
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r77_fixtures as FX  # noqa: E402
from agentic_alpha_lab.backtest.engine import run_backtest  # noqa: E402

CONFIG = json.loads((_ROOT / "configs" / "opencode_r77_fixtures.json").read_text())
TOL = CONFIG["tolerance"]


def feed_records(n, start="2026-01-05T01:00:00Z", symbol="BTCUSDT", closed=True,
                 with_observed=True):
    start_ts = pd.Timestamp(start, tz="UTC")
    recs = []
    for i in range(n):
        ot = start_ts + pd.Timedelta(minutes=5 * i)
        rec = {"open_time": ot,
               "close_time": ot + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
               "open": 100.0, "high": 100.4, "low": 99.6, "close": 100.0,
               "volume": 10.0, "symbol": symbol, "is_closed": closed}
        if with_observed:
            rec["observed_at"] = (ot + pd.Timedelta(minutes=5)).isoformat()
        recs.append(rec)
    return recs


# --------------------------------------------------------------------------
# (1) Feed contract
# --------------------------------------------------------------------------

def test_feed_closed_only():
    recs = feed_records(2, closed=True)
    recs[1] = {**recs[1], "is_closed": False}
    accepted, rejected = FX.ingest_feed(recs)
    assert len(accepted) == 1
    assert [r["code"] for r in rejected] == ["INCOMPLETE"]


def test_feed_fresh_requires_observed_at():
    recs = feed_records(2, with_observed=False)
    accepted, rejected = FX.ingest_feed(recs, manifest_kind="FRESH")
    assert len(accepted) == 0
    assert all(r["code"] == "INCOMPLETE" for r in rejected)
    # Same bytes as REPLAY are ingestible (diagnostic, not actionable).
    accepted_r, rejected_r = FX.ingest_feed(recs, manifest_kind="REPLAY")
    assert len(accepted_r) == 2 and rejected_r == []


def test_feed_stale_rejected():
    recs = feed_records(3)
    watermark = recs[1]["close_time"]
    accepted, rejected = FX.ingest_feed(recs, watermark_close=watermark)
    assert [r["code"] for r in rejected] == ["STALE", "STALE"]
    assert len(accepted) == 1


def test_feed_duplicate_rejected():
    recs = feed_records(2)
    accepted, rejected = FX.ingest_feed(recs + [recs[0]])
    assert len(accepted) == 2
    assert [r["code"] for r in rejected] == ["DUPLICATE"]


def test_feed_out_of_order_rejected():
    recs = feed_records(3)
    shuffled = [recs[0], recs[2], recs[1]]  # bar1 arrives after bar2, unseen
    accepted, rejected = FX.ingest_feed(shuffled)
    assert len(accepted) == 2
    assert [r["code"] for r in rejected] == ["OUT_OF_ORDER"]


def test_feed_incomplete_missing_close():
    recs = feed_records(1)
    recs[0] = {**recs[0], "close_time": None}
    accepted, rejected = FX.ingest_feed(recs)
    assert len(accepted) == 0
    assert [r["code"] for r in rejected] == ["INCOMPLETE"]


def test_feed_market_mismatch_rejected():
    recs = feed_records(1, symbol="ETHUSDT")
    accepted, rejected = FX.ingest_feed(recs, expected_market="BTCUSDT")
    assert len(accepted) == 0
    assert [r["code"] for r in rejected] == ["MARKET_MISMATCH"]


def test_feed_manifest_replay_vs_fresh():
    candles, _, _ = FX.build_F1()
    fresh = FX.make_manifest("FRESH", candles, observed_at="2026-01-05T02:00:00Z")
    replay = FX.make_manifest("REPLAY", candles)
    assert fresh["is_replay"] is False and "observed_at" in fresh
    assert replay["is_replay"] is True and "observed_at" not in replay
    assert fresh["range"] == replay["range"]  # same bytes, different meaning
    with pytest.raises(ValueError):
        FX.make_manifest("FRESH", candles)  # no observed_at -> fail closed


# --------------------------------------------------------------------------
# (2) Execution fixtures certified against the audited engine
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fid", sorted(FX.BUILDERS))
def test_fixture_hand_matches_engine(fid):
    rec = FX.certify_fixture(fid)
    assert rec["mismatches"] == [], f"{fid}: {rec['mismatches']}"
    assert rec["certified"] is True


def test_f5_stop_first_skips_tp1():
    candles, signals, _ = FX.build_F5()
    _, trades = run_backtest(candles, signals, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    t = trades[0]
    # Full-stop PnL on whole notional: TP1 contributed nothing despite the touch.
    assert t.gross_pnl == pytest.approx((98.5 - 100.0) / 100.0 * 100.0, abs=TOL)
    assert t.exit_reason == "stop" and t.exit_index == 2


def test_f6_suppression_is_observable():
    candles, signals, _ = FX.build_F6()
    _, trades = run_backtest(candles, signals, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    t = trades[0]
    # Entry bar touched TP1=101 but targets were suppressed (entry not at open):
    # TP1 filled next bar @max(101.2,101)=101.2, not @101 on the entry bar.
    assert t.gross_pnl == pytest.approx(2.1, abs=TOL)
    assert t.gross_pnl != pytest.approx(FX.HAND_EXPECTED["F6_suppression"]["naive_no_suppression_gross"])


def test_f8_funding_long_charged_short_zero():
    candles, signals, _ = FX.build_F8()
    _, trades = run_backtest(candles, signals, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    assert trades[0].funding == pytest.approx(0.01005, abs=TOL)
    _, signals_s, _ = FX.build_F8s()
    _, trades_s = run_backtest(candles, signals_s, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    assert trades_s[0].funding == 0.0


def test_f9_expiry_no_fill():
    candles, signals, _ = FX.build_F9()
    result, trades = run_backtest(candles, signals, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    assert trades == [] and result.rejected_or_unfilled_signals == 1
    assert result.final_equity == pytest.approx(FX.EQUITY0, abs=TOL)


# --------------------------------------------------------------------------
# (3) Scenarios per fixture
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fid", sorted(FX.BUILDERS))
def test_fixture_three_scenarios(fid):
    candles, signals, _ = FX.BUILDERS[fid]()
    out = FX.run_scenarios(candles, signals)
    assert set(out) == {"normal", "fee_stress", "execution_stress"}
    normal_n = out["normal"]["result"]["trades"]
    # Fee stress never creates fills the normal run lacks (fees only).
    assert out["fee_stress"]["result"]["trades"] == normal_n
    assert out["fee_stress"]["result"]["fees"] >= out["normal"]["result"]["fees"] - TOL
    # Execution-stress path runs the versioned stress simulator end to end.
    assert out["execution_stress"]["diagnostics"]["engine"] == "ohlc-stress-v1"
    assert "warning" in out["execution_stress"]["diagnostics"]


def test_unsupported_scenarios_disclosed_and_global_pass_withheld():
    assert CONFIG["global_pass"] is False
    assert len(CONFIG["unsupported_scenarios"]) >= 1
    payload = FX.certify_all(write=False)
    assert payload["global_pass"] is False
    assert "WITHHELD" in payload["global_pass_reason"]
    assert any("liquidation" in u for u in payload["unsupported"])


# --------------------------------------------------------------------------
# Restart: pending intent + partial position
# --------------------------------------------------------------------------

def test_f10_pending_restart():
    rec = FX.check_pending_restart()
    assert rec["certified"] is True, rec
    assert rec["status"] == "FILLED"
    assert rec["resumed_entry"][0] == rec["engine_entry"][0]
    assert rec["stale_status"] == "EXPIRED"


def test_f11_partial_restart_matches_engine():
    rec = FX.check_partial_restart()
    assert rec["mismatches"] == [], rec["mismatches"]
    assert rec["certified"] is True
    assert rec["resumed"]["remaining"] == 0.0
    assert rec["resumed"]["exit_reason"] == "tp2"


# --------------------------------------------------------------------------
# (4) Negative controls: verifier must FAIL on doctored doubles
# --------------------------------------------------------------------------

def _engine_record():
    candles, signals, _ = FX.build_F1()
    _, trades = run_backtest(candles, signals, FX.EQUITY0, FX.normal_costs(), FX.std_execution())
    return FX.trade_record(trades[0])


def test_verifier_positive_control_passes():
    rec = _engine_record()
    verdict = FX.verify_parity(rec, copy.deepcopy(rec))
    assert verdict.pass_ is True and verdict.reasons == []


def test_verifier_rejects_wrong_tp1_fraction():
    expected, actual = _engine_record(), _engine_record()
    # Double computed with tp1_fraction=0.75 instead of frozen 0.5.
    expected["gross_pnl"] = 0.75 * 1.0 + 0.25 * 3.0
    expected["remaining"] = 0.25
    verdict = FX.verify_parity(expected, actual)
    assert verdict.pass_ is False
    assert any("gross_pnl" in r or "remaining" in r for r in verdict.reasons)


def test_verifier_rejects_wrong_fee():
    expected, actual = _engine_record(), _engine_record()
    expected["fees"] = 100 * 0.00055 + 50 * 1.01 * 0.00055 + 50 * 1.03 * 0.00055
    verdict = FX.verify_parity(expected, actual)
    assert verdict.pass_ is False
    assert any("fees" in r for r in verdict.reasons)


def test_verifier_rejects_shifted_entry_timestamp():
    expected, actual = _engine_record(), _engine_record()
    shifted = pd.Timestamp(actual["entry_time"]) + pd.Timedelta(minutes=5)
    actual["entry_time"] = shifted.isoformat()
    verdict = FX.verify_parity(expected, actual)
    assert verdict.pass_ is False
    assert any("entry_time" in r for r in verdict.reasons)


def test_verifier_rejects_wrong_control_routing():
    expected, actual = _engine_record(), _engine_record()
    actual["account"] = "control"  # control equity routed as operating
    actual["equity_after"] = actual["equity_after"] + 0.5
    verdict = FX.verify_parity(expected, actual)
    assert verdict.pass_ is False
    assert any("account" in r or "equity_after" in r for r in verdict.reasons)
