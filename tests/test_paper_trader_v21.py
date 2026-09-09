"""Tests for scripts/opencode_paper_trader_v21.py (paper-only, v2.1 fixes).

EXPLORATORY. Synthetic part is deterministic on synthetic bars (no network, no
exchange code, no credentials, no registry writes). Real-data part replays 100%
real frozen artifacts (Track-C candles + frozen signals + frozen baselines) to
prove the one-sided trip + resume semantics on non-synthetic data.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencode_paper_trader as v1  # noqa: E402
import opencode_paper_trader_v2 as v2  # noqa: E402
import opencode_paper_trader_v21 as v21  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
START, END = 177690, 443001  # long Track-C replay window (265311 bars)


# -- synthetic fixtures (mirror v2 tests) ------------------------------------
def make_candles_ohlc(rows, start="2025-01-01T23:30:00+00:00"):
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
    return pd.DataFrame([{"bar_index": s[0], "direction": s[1], "entry_limit": s[2],
                          "stop_loss": s[3], "take_profit_2": s[4], "holding_bars": s[5],
                          "ohlc_fill_score": s[6]} for s in specs])


def write_trades_csv(path, rows):
    """rows: list of (signal_index, exit_index, equity_after)."""
    path.write_text(
        "signal_index,direction,leverage,entry_index,entry_time,entry_price,"
        "exit_index,exit_time,exit_reason,gross_pnl,fees,funding,net_pnl,"
        "equity_before,equity_after,holding_bars,liquidation_price\n" + "".join(
            f"{s},1,1.0,{s + 1},t,100,{e},t,tp,0,0,0,0,100,{eq},10,\n"
            for s, e, eq in rows))


def base_config_v21(signals_path, baseline_trades, baseline_signals,
                    divergence_tol=0.05, min_conf=0.0, halt_x=0.03, drill=None):
    dv = {"baseline": str(baseline_trades), "baseline_signals": str(baseline_signals),
          "tolerance_pct": divergence_tol, "initial_equity": 100.0,
          "latch": True, "one_sided": "UNDER_ONLY"}
    if drill is not None:
        dv["crossbook_drill"] = drill
    return {"mode": "SIMULATED/PAPER", "allow_live_orders": False,
            "guard": {"dd_trigger": 0.10, "guard_leverage": 0.5, "full_leverage": 1.0},
            "costs": {"fee_rate_per_fill": 0.0, "funding_long_rate": 0.0,
                      "funding_short_rate": 0.0, "funding_interval_hours": 8},
            "policy_geometry": {"min_confidence": min_conf, "entry_expiry_bars": 12,
                                "max_holding_bars": 50},
            "account": {"initial_equity_indexed": 100.0},
            "kill_switch": {"daily_loss_halt_pct": halt_x, "max_positions": 1},
            "divergence": dv,
            "state": {"persist_path": "synthetic-state", "alert_log": "synthetic-alerts",
                      "persist_every_n_bars": 1},
            "live_feed": {"enabled": False}}


def make_v21(signals_df, config, tmp_files=None, n_bars=None, curve=None):
    return v21.PaperStrategyV21(v1.ReplayPredictor(signals_df), config,
                                expected_curve=curve, n_bars=n_bars)


def walk(strategy, candles, start=0, end=None):
    for i in range(start, len(candles) if end is None else end):
        strategy.on_bar(candles.iloc[:i + 1])
    return strategy


def signal_bars(strategy):
    return [it["signal_bar"] for it in strategy.intents]


def matching_setup(tmp_path, specs, trades_rows):
    """Signals parquet + trades csv describing the SAME book. Returns paths."""
    sig = make_signals(specs)
    sig_path = tmp_path / "signals.parquet"
    sig.to_parquet(sig_path)
    tr_path = tmp_path / "normal_trades.csv"
    write_trades_csv(tr_path, trades_rows)
    return sig, sig_path, tr_path


# -- (1) same-book baseline identity ------------------------------------------
def test_identity_passes_for_same_book(tmp_path):
    specs = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9), (20, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(2, 5, 101.0), (20, 25, 102.0)])
    strat = make_v21(sig, base_config_v21(sig_path, tr_path, sig_path), n_bars=30)
    assert strat.identity_report["identity"] is True
    assert strat.identity_report["fingerprint_match"] is True
    assert strat.identity_report["n_missing"] == 0
    assert strat.is_drill is False
    walk(strat, make_candles_ohlc(flat(30)), end=30)
    v21.verify_intents_v21(strat.intents_df(), strat)


def test_silent_mismatch_refused_fail_closed(tmp_path):
    specs_a = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    specs_b = [(7, 1, 100.0, 50.0, 1e9, 3, 0.9)]  # different book
    sig_a = make_signals(specs_a)
    sig_b_path = tmp_path / "other_signals.parquet"
    make_signals(specs_b).to_parquet(sig_b_path)
    tr_path = tmp_path / "normal_trades.csv"
    write_trades_csv(tr_path, [(7, 9, 101.0)])
    cfg = base_config_v21(tmp_path / "a.parquet", tr_path, sig_b_path)
    with pytest.raises(ValueError, match="signal-set mismatch"):
        make_v21(sig_a, cfg, n_bars=30)


def test_missing_baseline_trade_refused_even_with_matching_fingerprint(tmp_path):
    specs = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(2, 5, 101.0), (99, 105, 102.0)])
    # fingerprint matches (same file) but trade 99 never replayed -> refuse
    assert v21.fingerprint_signals(sig) == v21.fingerprint_signals_file(sig_path)
    with pytest.raises(ValueError, match="signal-set mismatch"):
        make_v21(sig, base_config_v21(sig_path, tr_path, sig_path), n_bars=120)


def test_declared_crossbook_drill_allowed_and_labelled(tmp_path):
    specs_a = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig_a = make_signals(specs_a)
    other_path = tmp_path / "other_signals.parquet"
    make_signals([(7, -1, 100.0, 150.0, 10.0, 3, 0.9)]).to_parquet(other_path)
    tr_path = tmp_path / "normal_trades.csv"
    write_trades_csv(tr_path, [(7, 9, 101.0)])
    drill = {"declared": True, "reason": "synthetic drill declaration",
             "expected_effect": "runs with drill label"}
    strat = make_v21(sig_a, base_config_v21(tmp_path / "a.parquet", tr_path, other_path,
                                            drill=drill), n_bars=30)
    assert strat.is_drill is True
    assert strat.identity_report["identity"] is False
    assert any(a.get("kind") == "CROSSBOOK_DRILL" for a in strat.alerts)
    rep = v21.verify_intents_v21(strat.intents_df(), strat)
    assert rep["v21_is_drill"] is True


def test_malformed_drill_declaration_refused(tmp_path):
    specs = [(2, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(2, 5, 101.0)])
    bad = base_config_v21(sig_path, tr_path, sig_path,
                          drill={"declared": True, "reason": "   "})
    with pytest.raises(ValueError):
        make_v21(sig, bad, n_bars=30)


# -- (2) one-sided trip ---------------------------------------------------------
def test_trip_only_on_underperformance_not_overperformance(tmp_path):
    rows = flat(12)
    rows[4] = (100.0, 100.0, 90.0, 100.0)  # stop run: LONG stopped ~94 -> UNDER trip
    candles = make_candles_ohlc(rows)
    specs = [(1, 1, 100.0, 94.0, 1e9, 50, 0.9),   # intent, enters bar 2, stopped bar 4
             (8, 1, 100.0, 50.0, 1e9, 50, 0.9)]   # after trip -> blocked
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(1, 6, 100.0)])
    cfg = base_config_v21(sig_path, tr_path, sig_path, divergence_tol=0.05)
    strat = make_v21(sig, cfg, n_bars=len(candles))
    walk(strat, candles, end=3)
    assert not strat.divergence.tripped
    walk(strat, candles, start=3)
    assert strat.divergence.tripped
    trip = strat.divergence.trip_event
    assert trip["direction"] == "UNDER" and trip["status"] == "TRIPPED_NOW"
    assert trip["divergence"] < -0.05
    assert signal_bars(strat) == [1] and strat.skipped_divergence == 1
    assert any(a.get("kind") == "DIVERGENCE_TRIP" and a.get("direction") == "UNDER"
               for a in strat.alerts)
    v21.verify_intents_v21(strat.intents_df(), strat)


def test_overperformance_logged_info_only_never_latches(tmp_path):
    rows = flat(14)
    rows[3] = (200.0, 200.0, 200.0, 200.0)  # gap up: TP fills -> equity ~200 (+100%)
    candles = make_candles_ohlc(rows)
    specs = [(1, 1, 100.0, 50.0, 150.0, 3, 0.9),
             (5, 1, 100.0, 50.0, 150.0, 3, 0.9),   # must still emit (no latch)
             (9, 1, 100.0, 50.0, 150.0, 3, 0.9)]   # must still emit (earlier timed out)
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(1, 6, 100.0)])
    strat = make_v21(sig, base_config_v21(sig_path, tr_path, sig_path, divergence_tol=0.05),
                     n_bars=len(candles))
    walk(strat, candles)
    assert not strat.divergence.tripped
    assert strat.divergence.trip_event is None
    assert signal_bars(strat) == [1, 5, 9]  # nothing blocked by divergence
    assert strat.skipped_divergence == 0
    assert len(strat.divergence.over_events) == 1  # logged exactly once
    over = strat.divergence.over_events[0]
    assert over["kind"] == "DIVERGENCE_OVER_INFO" and over["direction"] == "OVER"
    assert over["status"] == "INFO_ONLY" and over["divergence"] > 0.05
    assert any(a.get("kind") == "DIVERGENCE_OVER_INFO" for a in strat.alerts)
    v21.verify_intents_v21(strat.intents_df(), strat)


# -- (5) anti-live interlock extended -------------------------------------------
def test_anti_live_interlock_v21_extended(tmp_path, monkeypatch):
    specs = [(1, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(1, 6, 100.0)])
    good = lambda: base_config_v21(sig_path, tr_path, sig_path)  # noqa: E731
    cfg = good()
    cfg["allow_live_orders"] = True
    with pytest.raises(SystemExit):
        make_v21(sig, cfg, n_bars=8)
    cfg = good()
    cfg["live_feed"] = {"enabled": True}
    with pytest.raises(SystemExit):
        make_v21(sig, cfg, n_bars=8)
    cfg = good()  # secret-looking key under a v2.1-new section is refused
    cfg["divergence"]["crossbook_drill"] = {"declared": True, "reason": "x", "api_key": "x"}
    with pytest.raises(SystemExit):
        make_v21(sig, cfg, n_bars=8)
    cfg = good()  # network-looking value under a v2.1-new section is refused
    cfg["divergence"]["baseline_signals"] = "wss://example.invalid/stream"
    with pytest.raises(SystemExit):
        make_v21(sig, cfg, n_bars=8)
    for flag in ("--crossbook", "--skip-identity-check", "--force"):
        with monkeypatch.context() as m:
            m.setattr(sys, "argv", ["paper", flag])
            with pytest.raises(SystemExit):
                v21.assert_no_live_path_v21(good())
    walk(make_v21(sig, good(), n_bars=8), make_candles_ohlc(flat(8)))  # paper path runs clean


def test_v21_state_rejects_v2_snapshot_and_foreign_fingerprint(tmp_path):
    specs = [(1, 1, 100.0, 50.0, 1e9, 3, 0.9)]
    sig, sig_path, tr_path = matching_setup(tmp_path, specs, [(1, 6, 101.0)])
    cfg = base_config_v21(sig_path, tr_path, sig_path)
    strat = make_v21(sig, cfg, n_bars=30)
    walk(strat, make_candles_ohlc(flat(30)), end=10)
    state_file = tmp_path / "v21_state.json"
    strat.save_state(state_file)
    snap = json.loads(state_file.read_text())
    assert snap["version"] == v21.STATE_VERSION
    snap["version"] = v2.STATE_VERSION  # forged old version -> refuse
    fresh = make_v21(sig, cfg, n_bars=30)
    with pytest.raises(ValueError, match="version mismatch"):
        fresh.restore_state(snap)
    other = make_signals([(4, -1, 100.0, 150.0, 10.0, 3, 0.9)])
    other_path = tmp_path / "other.parquet"
    other.to_parquet(other_path)
    drill = {"declared": True, "reason": "fingerprint test", "expected_effect": ""}
    foreign = make_v21(other, base_config_v21(other_path, tr_path, other_path,
                                              drill=drill), n_bars=30)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        foreign.restore_state(json.loads(state_file.read_text()))


# -- demo configs carry the pre-specified parameters -----------------------------
def test_demo_configs_prespecified():
    operating = json.loads((ROOT / "configs/opencode_paper_trader_v21.json").read_text())
    alternate = json.loads((ROOT / "configs/opencode_paper_trader_v21_x2.json").read_text())
    drill = json.loads((ROOT / "configs/opencode_paper_trader_v21_drill_crossbook.json").read_text())
    drill2 = json.loads((ROOT / "configs/opencode_paper_trader_v21_drill_crossbook_x2.json").read_text())
    for cfg in (operating, alternate, drill, drill2):
        v21.assert_no_live_path_v21(cfg)
        assert cfg["divergence"]["tolerance_pct"] == pytest.approx(0.05)  # Y=5% pre-specified
        assert cfg["allow_live_orders"] is False and cfg["live_feed"]["enabled"] is False
        assert cfg["exploratory"] is True
    assert operating["kill_switch"]["daily_loss_halt_pct"] == pytest.approx(0.03)
    assert alternate["kill_switch"]["daily_loss_halt_pct"] == pytest.approx(0.02)
    for cfg in (operating, alternate):  # operating runs are statically same-book
        assert cfg["data"]["signals_replay_only"] == cfg["divergence"]["baseline_signals"]
        assert "crossbook_drill" not in cfg["divergence"]
    for cfg in (drill, drill2):
        assert cfg["divergence"]["crossbook_drill"]["declared"] is True


# -- real-data fixtures (frozen Track-C artifacts, read-only) --------------------
def _load_real():
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet")
    return candles.sort_values("open_time").reset_index(drop=True)


def _real_strategy(config_name, n_bars):
    cfg = json.loads((ROOT / "configs" / config_name).read_text())
    v21.assert_no_live_path_v21(cfg)
    signals = pd.read_parquet(ROOT / cfg["data"]["signals_replay_only"])
    return cfg, signals, v21.PaperStrategyV21(
        v1.ReplayPredictor(signals), cfg, n_bars=n_bars, root=ROOT)


# -- (3) real halt + real trip-block on non-synthetic replay data -----------------
def test_real_drill_trip_blocks_later_real_signals():
    candles = _load_real()
    cfg, signals, strat = _real_strategy(
        "opencode_paper_trader_v21_drill_crossbook.json", len(candles))
    assert strat.is_drill is True and strat.identity_report["identity"] is False
    for i in range(START, END):
        strat.on_bar(candles.iloc[:i + 1])
    rep = v21.verify_intents_v21(strat.intents_df(), strat)
    assert rep["v21_one_sided_checks"] == "pass"
    assert strat.divergence.tripped, "drill must genuinely trip UNDER on real data"
    trip = strat.divergence.trip_event
    assert trip["direction"] == "UNDER" and trip["divergence"] < -0.05
    real_bars = set(int(b) for b in signals["bar_index"].tolist())
    assert strat.skipped_divergence >= 1, "trip must block a later real signal"
    assert signal_bars(strat) and max(signal_bars(strat)) < int(trip["bar_idx"])
    # over-excursion happened first but never latched (one-sided field evidence)
    assert len(strat.divergence.over_events) == 1
    assert int(strat.divergence.over_events[0]["bar_idx"]) < int(trip["bar_idx"])
    # real halt days fired AND a real signal falls in a halted day
    halt_days = {e["day"] for e in strat.daily_halt.halt_events}
    assert len(halt_days) >= 1
    in_halt = [b for b in real_bars
               if pd.Timestamp(candles["open_time"].iloc[b]).date().isoformat() in halt_days]
    assert len(in_halt) >= 1, "at least one real signal falls in a halted day"


# -- (4) resume on the LONG Track-C replay: identical continuation -----------------
def test_resume_long_trackc_replay_identical():
    candles = _load_real()
    n = len(candles)
    mid = START + (END - START) // 2
    _, _, cont = _real_strategy("opencode_paper_trader_v21.json", n)
    for i in range(START, END):
        cont.on_bar(candles.iloc[:i + 1])
    assert cont.identity_report["identity"] is True and not cont.divergence.tripped
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        state_file = Path(td) / "kill_state.json"
        _, _, part = _real_strategy("opencode_paper_trader_v21.json", n)
        for i in range(START, mid):
            part.on_bar(candles.iloc[:i + 1])
        part.save_state(state_file)  # KILL mid-run
        _, _, resumed = _real_strategy("opencode_paper_trader_v21.json", n)
        resumed.restore_state(v2.load_state_file(str(state_file)))
        assert resumed.account.equity == pytest.approx(part.account.equity)
        for i in range(mid, END):
            resumed.on_bar(candles.iloc[:i + 1])
    pd.testing.assert_frame_equal(resumed.intents_df(), cont.intents_df())
    assert resumed.account.equity == pytest.approx(cont.account.equity)
    assert resumed.account.exits == cont.account.exits
    assert resumed.signals_seen == cont.signals_seen
    assert resumed.skipped_busy == cont.skipped_busy
    assert resumed.skipped_daily_halt == cont.skipped_daily_halt
    assert resumed.skipped_divergence == cont.skipped_divergence
    assert resumed.daily_halt.halt_events == cont.daily_halt.halt_events
    assert resumed.divergence.checks == cont.divergence.checks
    assert resumed.divergence.tripped == cont.divergence.tripped
    assert resumed.alerts == cont.alerts
    assert resumed.day_closes == cont.day_closes
    assert [h["state"] for h in resumed.guard.history] == \
        [h["state"] for h in cont.guard.history]
