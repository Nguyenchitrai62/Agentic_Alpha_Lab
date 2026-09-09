"""Tests for scripts/opencode_paper_trader_v2.py (paper-only bot infra).

EXPLORATORY. All deterministic on synthetic bars: no network, no exchange code,
no credentials, no registry writes. Each test isolates one halt/trip/guard.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)

import inspect
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencode_paper_trader as v1  # noqa: E402
import opencode_paper_trader_v2 as v2  # noqa: E402


# -- synthetic fixtures ------------------------------------------------------
def make_candles_ohlc(rows, start="2025-01-01T23:30:00+00:00"):
    """rows: list of (o, h, l, c). Positional index acts as synthetic bar_index."""
    idx = pd.date_range(start=start, periods=len(rows), freq="5min", tz="UTC")
    o, h, l, c = zip(*rows)
    df = pd.DataFrame({"open_time": list(idx), "open": [float(x) for x in o],
                       "high": [float(x) for x in h], "low": [float(x) for x in l],
                       "close": [float(x) for x in c], "volume": [1.0] * len(rows),
                       "close_time": list(idx + pd.Timedelta(minutes=5)
                                          - pd.Timedelta(milliseconds=1))})
    return df.reset_index(drop=True)


def flat(n, price=100.0):
    return [(price, price, price, price)] * n


def make_signals(specs):
    """specs: list of (bar_index, direction, entry_limit, stop, tp, holding, score)."""
    return pd.DataFrame([{"bar_index": s[0], "direction": s[1], "entry_limit": s[2],
                          "stop_loss": s[3], "take_profit_2": s[4], "holding_bars": s[5],
                          "ohlc_fill_score": s[6]} for s in specs])


def base_config(divergence_tol=0.5, min_conf=0.0, max_holding=50):
    return {"mode": "SIMULATED/PAPER", "allow_live_orders": False,
            "guard": {"dd_trigger": 0.10, "guard_leverage": 0.5, "full_leverage": 1.0},
            "costs": {"fee_rate_per_fill": 0.0, "funding_long_rate": 0.0,
                      "funding_short_rate": 0.0, "funding_interval_hours": 8},
            "policy_geometry": {"min_confidence": min_conf, "entry_expiry_bars": 12,
                                "max_holding_bars": max_holding},
            "account": {"initial_equity_indexed": 100.0},
            "kill_switch": {"daily_loss_halt_pct": 0.03, "max_positions": 1},
            "divergence": {"baseline": "synthetic-test-curve", "tolerance_pct": divergence_tol,
                           "initial_equity": 100.0},
            "state": {"persist_path": "synthetic-state", "alert_log": "synthetic-alerts",
                      "persist_every_n_bars": 1},
            "live_feed": {"enabled": False}}


def make_strategy(signals_df, config, curve=None, n_bars=None):
    if curve is None:
        curve = ([], [])  # flat expected 100.0 via initial_equity
    return v2.PaperStrategyV2(v1.ReplayPredictor(signals_df), config,
                              expected_curve=curve, n_bars=n_bars)


def walk(strategy, candles, start=0, end=None):
    for i in range(start, len(candles) if end is None else end):
        strategy.on_bar(candles.iloc[:i + 1])
    return strategy


def signal_bars(strategy):
    return [it["signal_bar"] for it in strategy.intents]


# -- (1) event-driven interface ----------------------------------------------
def test_event_interface_shared_by_replay_and_live():
    assert issubclass(v2.PaperStrategyV2, object)
    assert "on_bar" in v2.Strategy.__protocol_attrs__ if hasattr(v2.Strategy, "__protocol_attrs__") \
        else hasattr(v2.Strategy, "on_bar")
    sig = inspect.signature(v2.PaperStrategyV2.on_bar)
    assert list(sig.parameters)[1] == "closed_bars_df"  # single entry point
    rows = flat(30)
    candles = make_candles_ohlc(rows)
    specs = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9), (20, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    # Replay style: slices of the full frame.
    strat_replay = make_strategy(make_signals(specs), base_config(), n_bars=len(candles))
    walk(strat_replay, candles)
    # Live-feed style: incrementally appended frame (same columns/index contract).
    strat_live = make_strategy(make_signals(specs), base_config(), n_bars=len(candles))
    frame = candles.iloc[:0].copy()
    for i in range(len(candles)):
        frame = pd.concat([frame, candles.iloc[[i]]])
        strat_live.on_bar(frame)
    assert signal_bars(strat_live) == signal_bars(strat_replay) == [2, 20]
    assert strat_live.account.equity == pytest.approx(strat_replay.account.equity)


# -- (2) kill-switch: DailyLossHalt -------------------------------------------
def test_daily_loss_halt_blocks_rest_of_day_then_clears_next_day():
    rows = flat(12)
    rows[4] = (100.0, 100.0, 90.0, 100.0)  # stop run: LONG stopped at 95 -> equity 95
    candles = make_candles_ohlc(rows)  # bars 0-5 on 2025-01-01, bars 6+ on 2025-01-02
    specs = [(1, 1, 100.0, 95.0, 1e9, 50, 0.9),   # intent, enters bar 2, stopped bar 4
             (5, 1, 100.0, 95.0, 1e9, 50, 0.9),   # same UTC day, AFTER halt -> blocked
             (8, 1, 100.0, 95.0, 1e9, 50, 0.9)]   # next UTC day -> allowed
    strat = make_strategy(make_signals(specs), base_config(divergence_tol=0.5), n_bars=len(candles))
    walk(strat, candles)
    assert signal_bars(strat) == [1, 8]
    assert len(strat.daily_halt.halt_events) == 1
    ev = strat.daily_halt.halt_events[0]
    assert ev["day"] == "2025-01-01" and ev["kind"] == "DAILY_LOSS_HALT"
    assert ev["drawdown_pct"] == pytest.approx(0.05)  # 100 -> 95, over the X=3% trip
    assert strat.skipped_daily_halt == 1
    assert any(a.get("kind") == "DAILY_LOSS_HALT" for a in strat.alerts)
    assert strat.account.equity == pytest.approx(95.0)
    v2.verify_intents_v2(strat.intents_df(), strat)  # no intent after the halt time


# -- (2b) kill-switch: MaxPositionGuard ----------------------------------------
def test_max_position_guard_single_position_fail_closed():
    candles = make_candles_ohlc(flat(8))
    specs = [(1, 1, 1.0, 0.5, 1e9, 50, 0.9),   # limit far away: pending, never fills
             (2, 1, 100.0, 50.0, 1e9, 50, 0.9)]  # blocked: one paper position at a time
    strat = make_strategy(make_signals(specs), base_config(), n_bars=len(candles))
    walk(strat, candles)
    assert signal_bars(strat) == [1]
    assert strat.skipped_busy == 1
    assert v2.MaxPositionGuard.count(strat.account) == 1
    v2.MaxPositionGuard.assert_invariant(strat.account)  # holds while legal
    strat.account.open = {"injected": True}  # force pending AND open: must fail closed
    with pytest.raises(AssertionError):
        v2.MaxPositionGuard.assert_invariant(strat.account)
    with pytest.raises(AssertionError):
        v2.MaxPositionGuard.blocks_new_intent(strat.account)


# -- (3) divergence-trip --------------------------------------------------------
def test_divergence_trip_latches_and_alerts():
    rows = flat(10)
    rows[3] = (200.0, 200.0, 200.0, 200.0)  # gap up: TP fills at 200 -> equity 200
    candles = make_candles_ohlc(rows)
    specs = [(1, 1, 100.0, 50.0, 150.0, 50, 0.9),  # intent, enters bar 2 @100, TP bar 3 @200
             (5, 1, 100.0, 50.0, 150.0, 50, 0.9),  # after trip -> blocked
             (6, 1, 100.0, 50.0, 150.0, 50, 0.9)]  # latch persists -> blocked
    strat = make_strategy(make_signals(specs), base_config(divergence_tol=0.05), n_bars=len(candles))
    walk(strat, candles, end=3)  # bars 0..2: entered, not yet exited
    assert not strat.divergence.tripped
    assert signal_bars(strat) == [1]
    walk(strat, candles, start=3)  # bar 3 settles the TP exit -> trip
    assert strat.divergence.tripped
    trip = strat.divergence.trip_event
    assert trip["bar_idx"] == 3 and trip["status"] == "TRIPPED_NOW"
    assert trip["paper_equity"] == pytest.approx(200.0)
    assert trip["expected_equity"] == pytest.approx(100.0)
    assert trip["divergence"] == pytest.approx(1.0)
    assert signal_bars(strat) == [1]  # post-trip signals blocked, never emitted
    assert strat.skipped_divergence == 2
    assert strat.divergence.tripped  # latch persists across further bars
    assert any(a.get("kind") == "DIVERGENCE_TRIP" for a in strat.alerts)
    v2.verify_intents_v2(strat.intents_df(), strat)


# -- (4) state persistence -------------------------------------------------------
def test_state_persistence_roundtrip(tmp_path):
    rows = flat(12)
    rows[4] = (100.0, 100.0, 90.0, 100.0)
    candles = make_candles_ohlc(rows)
    specs = [(1, 1, 100.0, 95.0, 1e9, 50, 0.9), (8, 1, 100.0, 95.0, 1e9, 50, 0.9)]
    cfg = base_config(divergence_tol=0.5)
    state_file = tmp_path / "guard_halt_state.json"
    cont = make_strategy(make_signals(specs), cfg, n_bars=len(candles))
    walk(cont, candles, end=6)  # through the bar-4 exit + day-1 halt
    cont.save_state(state_file)
    snap = json.loads(state_file.read_text())
    assert snap["version"] == v2.STATE_VERSION and snap["mode"] == v2.MODE_LABEL
    resumed = make_strategy(make_signals(specs), cfg, n_bars=len(candles))
    resumed.restore_state(v2.load_state_file(state_file))
    assert resumed.account.equity == pytest.approx(cont.account.equity)
    assert resumed.daily_halt.halted_day == cont.daily_halt.halted_day == "2025-01-01"
    assert signal_bars(resumed) == signal_bars(cont) == [1]
    assert resumed.snapshot_state()["counters"] == cont.snapshot_state()["counters"]
    walk(cont, candles, start=6)
    walk(resumed, candles, start=6)
    assert signal_bars(resumed) == signal_bars(cont) == [1, 8]
    assert resumed.account.equity == pytest.approx(cont.account.equity)
    assert resumed.divergence.checks == cont.divergence.checks
    assert resumed.daily_halt.halt_events == cont.daily_halt.halt_events


def test_load_expected_curve_forward_fill(tmp_path):
    p = tmp_path / "normal_trades.csv"
    p.write_text("signal_index,direction,leverage,entry_index,entry_time,entry_price,"
                 "exit_index,exit_time,exit_reason,gross_pnl,fees,funding,net_pnl,"
                 "equity_before,equity_after,holding_bars,liquidation_price\n"
                 "1,1,1.0,10,t,100,20,t,stop,0,0,0,0,100,90.0,10,\n"
                 "2,1,1.0,30,t,100,40,t,tp,0,0,0,0,90,110.0,10,\n")
    idx, eq = v2.load_expected_curve(p, 100.0)
    mon = v2.DivergenceMonitor(idx, eq, 0.05, 100.0)
    assert mon.expected_at(0) == pytest.approx(100.0)   # before first exit: seed
    assert mon.expected_at(20) == pytest.approx(90.0)
    assert mon.expected_at(39) == pytest.approx(90.0)   # stepwise forward-fill
    assert mon.expected_at(40) == pytest.approx(110.0)


# -- (5) anti-live interlock (extended to v2 paths) -------------------------------
def test_anti_live_interlock_extended(monkeypatch):
    candles = make_candles_ohlc(flat(3))
    sig = make_signals([(1, 1, 100.0, 50.0, 1e9, 3, 0.9)])
    cfg = base_config()
    cfg["allow_live_orders"] = True
    with pytest.raises(SystemExit):
        make_strategy(sig, cfg)
    cfg = base_config()
    cfg["live_feed"] = {"enabled": True}
    with pytest.raises(SystemExit):
        make_strategy(sig, cfg)
    cfg = base_config()
    cfg["live_feed"] = {"enabled": False, "api_url": "wss://example.invalid"}
    with pytest.raises(SystemExit):
        make_strategy(sig, cfg)
    cfg = base_config()
    cfg["kill_switch"] = {"daily_loss_halt_pct": 0.03, "max_positions": 1, "api_key": "x"}
    with pytest.raises(SystemExit):
        make_strategy(sig, cfg)
    with monkeypatch.context() as m:  # isolated env: restored on context exit
        m.setenv("BINANCE_API_KEY", "synthetic-not-a-secret")
        with pytest.raises(SystemExit):
            make_strategy(sig, base_config(), n_bars=len(candles))
    with monkeypatch.context() as m:  # isolated argv: restored on context exit
        m.setattr(sys, "argv", ["paper", "--live-feed"])
        with pytest.raises(SystemExit):
            v2.assert_no_live_path_v2(base_config())
    walk(make_strategy(sig, base_config(), n_bars=len(candles)), candles)  # paper path runs clean
