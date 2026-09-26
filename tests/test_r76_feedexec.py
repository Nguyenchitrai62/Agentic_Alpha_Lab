"""Tests for scripts/opencode_r76_feedexec.py (feed + execution core, paper only)."""
import torch  # noqa: F401  (import order: torch before pandas on this host)

import copy
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r76_feedexec as fx  # noqa: E402
from agentic_alpha_lab.backtest import engine as bt_engine  # noqa: E402

CONFIG = json.loads((_ROOT / "configs/opencode_r76_feedexec.json").read_text())
BASE_MS = int(pd.Timestamp("2023-01-02 01:00", tz="UTC").value // 10 ** 6)


def bar(i, o, h, lo, c, v=10.0, base_ms=BASE_MS):
    open_ms = base_ms + i * 300_000
    return {"open_time": pd.Timestamp(open_ms, unit="ms", tz="UTC"),
            "open": o, "high": h, "low": lo, "close": c, "volume": v,
            "close_time": pd.Timestamp(open_ms + 299_999, unit="ms", tz="UTC")}


def frame(rows):
    return pd.DataFrame(rows).reset_index(drop=True)


def long_signal(bar_idx=0, entry=100.0, sl=90.0, tp1=110.0, tp2=120.0,
                holding=10, lev=1.0, equity=100.0):
    return {"signal_bar": bar_idx, "direction": 1, "entry_limit": entry,
            "stop_loss": sl, "take_profit_1": tp1, "take_profit_2": tp2,
            "holding_bars": holding, "leverage": lev, "notional": equity * lev,
            "equity_before": equity}


def account(name="test"):
    c = CONFIG
    return fx.FeedExecAccount(100.0, c["costs"]["fee_rate_per_fill"],
                              c["costs"]["funding_long_rate"],
                              c["costs"]["funding_short_rate"],
                              c["costs"]["funding_interval_hours"],
                              c["execution"]["entry_expiry_bars"],
                              c["execution"]["tp1_fraction"], name)


# ------------------------------------------------------------- feed ---
def test_official_usdm_endpoint():
    url = fx.build_klines_url()
    assert url == "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=500"
    assert fx.FAPI_HOST == CONFIG["feed"]["host"] == "https://fapi.binance.com"
    assert fx.FAPI_PATH == CONFIG["feed"]["path"] == "/fapi/v1/klines"
    assert CONFIG["feed"]["host"] != "https://api.binance.com"
    assert CONFIG["feed"]["path"] != "/api/v3/klines"
    assert "api.binance.com/api/v3/klines" in CONFIG["feed"]["prior_fix"]  # old misuse disclosed
    assert "developers.binance.com" in CONFIG["feed"]["doc_ref"]


def test_parse_drops_forming_candle():
    raw = [[BASE_MS, "100", "101", "99", "100", "5", BASE_MS + 299_999],
           [BASE_MS + 300_000, "100", "102", "99", "101", "6", BASE_MS + 599_999]]
    closed = fx.parse_closed_klines(raw, BASE_MS + 400_000, observed_at="t")
    assert len(closed) == 1 and closed[0]["observed_at"] == "t"
    assert closed[0]["row_hash"] == fx.row_hash(BASE_MS, 100, 101, 99, 100, 5)


def test_feed_reject_codes_distinct():
    st = fx.FeedState(warmup_bars=0)
    good = {**bar(0, 100, 101, 99, 100), "symbol": "BTCUSDT",
            "interval": "5m", "market": "USDM", "observed_at": "t",
            "row_hash": fx.row_hash(BASE_MS, 100, 101, 99, 100, 10.0)}
    assert st.validate(good) == fx.STATUS_OK
    assert st.validate(good) == fx.STATUS_DUPLICATE
    conflict = {**good, "row_hash": "0" * 64, "close": 100.5}
    assert st.validate(conflict) == fx.STATUS_STALE
    older = {**bar(0, 100, 101, 99, 100), "symbol": "BTCUSDT", "interval": "5m",
             "market": "USDM", "observed_at": "t", "row_hash": "1" * 64}
    older["open_time"] = pd.Timestamp(BASE_MS - 300_000, unit="ms", tz="UTC")
    assert st.validate(older) == fx.STATUS_OUT_OF_ORDER
    bad = {**good, "row_hash": "2" * 64, "high": 90.0}
    assert st.validate(bad) == fx.STATUS_INCOMPLETE
    wrong = {**bar(5, 100, 101, 99, 100), "symbol": "ETHUSDT", "interval": "5m",
             "market": "USDM", "observed_at": "t", "row_hash": "3" * 64}
    assert st.validate(wrong) == fx.STATUS_MARKET_MISMATCH
    codes = {fx.STATUS_OK, fx.STATUS_DUPLICATE, fx.STATUS_STALE,
             fx.STATUS_OUT_OF_ORDER, fx.STATUS_INCOMPLETE, fx.STATUS_MARKET_MISMATCH}
    assert len(codes) == 6


def test_feed_warmup_and_clock():
    st = fx.FeedState(warmup_bars=2)
    mk = lambda i: {**bar(i, 100, 101, 99, 100), "symbol": "BTCUSDT",
                    "interval": "5m", "market": "USDM", "observed_at": "t",
                    "row_hash": fx.row_hash(BASE_MS + i * 300_000, 100, 101, 99, 100, 10.0)}
    assert st.validate(mk(0)) == fx.STATUS_WARMUP
    assert st.validate(mk(1)) == fx.STATUS_WARMUP
    assert st.validate(mk(2)) == fx.STATUS_OK
    assert fx.should_decide(12, 0, 12) and not fx.should_decide(13, 0, 12)


def test_fresh_mode_refuses_replay_inputs():
    with pytest.raises(ValueError, match="REFUSES replay inputs"):
        fx.build_manifest("fresh", config=CONFIG, source={"signals": "s.parquet"},
                          feed_state=fx.FeedState(),
                          clock={"anchor": 0, "stride": 12})
    m = fx.build_manifest("fresh", config=CONFIG, source={"url": "u"},
                          feed_state=fx.FeedState(), clock={"anchor": 0, "stride": 12})
    r = fx.build_manifest("replay", config=CONFIG,
                          source={"candles": "c", "signals": "s"},
                          feed_state=fx.FeedState(), clock={"anchor": 0, "stride": 12})
    assert m["kind"] == "FRESH-OBSERVATION" and r["kind"] == "REHEARSAL-NOT-LIVE"


# -------------------------------------------------------- execution ---
def test_tp1_then_tp2_split_accounting():
    ac = account()
    candles = frame([bar(0, 100, 100, 100, 100),
                     bar(1, 99, 101, 98, 100),
                     bar(2, 100, 112, 99, 111),
                     bar(3, 111, 121, 110, 120),
                     bar(4, 120, 120, 119, 119)])
    ac.on_bar_close(0, candles.iloc[0])  # signal bar settles before the signal exists
    assert ac.arm_pending(long_signal()) == "ARMED"
    evs = []
    for i in range(1, len(candles)):
        evs.extend(ac.on_bar_close(i, candles.iloc[i]))
    exits = [e for e in evs if e["kind"] == "EXIT"]
    assert [e["reason"] for e in exits] == ["tp1", "tp2"]
    assert exits[0]["fraction"] == pytest.approx(0.5)
    assert exits[1]["fraction"] == pytest.approx(0.5)
    exp = (100 - 0.02 + (11 / 99 * 50 - 100 * 0.5 * (110 / 99) * 0.0002)
           + (21 / 99 * 50 - 100 * 0.5 * (120 / 99) * 0.0002))
    assert ac.equity == pytest.approx(exp, rel=1e-9)
    assert ac.open is None and ac.exits == 1


def test_stop_first_over_tp():
    ac = account()
    candles = frame([bar(0, 100, 100, 100, 100),
                     bar(1, 99, 101, 98, 100),
                     bar(2, 105, 125, 85, 100),
                     bar(3, 100, 101, 99, 100)])
    ac.on_bar_close(0, candles.iloc[0])
    ac.arm_pending(long_signal())
    evs = []
    for i in range(1, len(candles)):
        evs.extend(ac.on_bar_close(i, candles.iloc[i]))
    exits = [e for e in evs if e["kind"] == "EXIT"]
    assert len(exits) == 1 and exits[0]["reason"] == "stop"
    assert exits[0]["fraction"] == pytest.approx(1.0)


def test_entry_bar_target_suppression():
    ac = account()
    candles = frame([bar(0, 100, 100, 100, 100),
                     bar(1, 102, 130, 99, 125),   # fills at limit, targets touched same bar
                     bar(2, 125, 131, 124, 130),
                     bar(3, 130, 132, 129, 131)])
    ac.on_bar_close(0, candles.iloc[0])
    ac.arm_pending(long_signal())
    evs = []
    for i in range(1, len(candles)):
        evs.extend(ac.on_bar_close(i, candles.iloc[i]))
    by_bar = {}
    for e in evs:
        by_bar.setdefault(e["bar_idx"], []).append(e["kind"])
    assert "EXIT" not in by_bar.get(1, [])
    assert ac.open is None  # tp1 bar2 + tp2 bar3


def test_expiry_cancel_and_truncated_window():
    ac = account()
    candles = frame([bar(i, 100, 101, 99, 100) for i in range(15)])
    ac.on_bar_close(0, candles.iloc[0])
    ac.arm_pending(long_signal(entry=50.0))
    evs = []
    for i in range(1, len(candles)):
        evs.extend(ac.on_bar_close(i, candles.iloc[i]))
    cancels = [e for e in evs if e["kind"] == "CANCEL"]
    assert len(cancels) == 1 and cancels[0]["reason"] == "expired"
    assert ac.rejected == 1 and ac.equity == pytest.approx(100.0)

    ac2 = account()
    tiny = frame([bar(0, 100, 100, 100, 100), bar(1, 99, 101, 98, 100)])
    ac2.on_bar_close(0, tiny.iloc[0])
    ac2.arm_pending(long_signal(holding=10))
    evs2 = [ac2.on_bar_close(1, tiny.iloc[1], n_bars=len(tiny))][0]
    assert evs2[-1]["reason"] == "truncated" and ac2.equity == pytest.approx(100.0)


def test_timeout_reasons():
    for hit_tp1, reason in ((True, "time_after_tp1"), (False, "time")):
        ac = account()
        rows = [bar(0, 100, 100, 100, 100), bar(1, 99, 101, 98, 100)]
        rows.append(bar(2, 100, 112 if hit_tp1 else 101, 99, 100))
        rows.append(bar(3, 107, 108, 106, 107))
        candles = frame(rows)
        ac.on_bar_close(0, candles.iloc[0])
        ac.arm_pending(long_signal(holding=2))
        evs = []
        for i in range(1, len(candles)):
            evs.extend(ac.on_bar_close(i, candles.iloc[i]))
        exits = [e for e in evs if e["kind"] == "EXIT"]
        assert exits[-1]["reason"] == reason, (hit_tp1, exits)


def test_restart_with_partial_and_pending():
    cfg = copy.deepcopy(CONFIG)
    cfg["decision_clock"]["stride_bars"] = 1
    mk = lambda: fx.FeedExecStrategy(cfg, n_bars=6)
    candles = frame([bar(0, 100, 100, 100, 100),
                     bar(1, 99, 101, 98, 100),
                     bar(2, 100, 112, 99, 111),
                     bar(3, 111, 121, 110, 120),
                     bar(4, 120, 120, 119, 119),
                     bar(5, 119, 120, 118, 119)])
    sig = long_signal(holding=3)
    dec = lambda: {"action": "LONG", "confidence": 1.0, "entry_limit": sig["entry_limit"],
                   "stop_loss": sig["stop_loss"], "take_profit_1": sig["take_profit_1"],
                   "take_profit_2": sig["take_profit_2"], "holding_bars": sig["holding_bars"]}
    ref = mk()
    for i in range(len(candles)):
        ref.on_bar(i, candles.iloc[i], dec() if i == 0 else None)
    cut = mk()
    for i in range(3):  # through TP1 bar: partial open + pending-free state to carry
        cut.on_bar(i, candles.iloc[i], dec() if i == 0 else None)
    assert cut.operating.open is not None and cut.operating.open["tp1_done"] is True
    snap = cut.snapshot_state()
    resumed = mk()
    resumed.restore_state(json.loads(json.dumps(snap, default=str)))
    for i in range(3, len(candles)):
        resumed.on_bar(i, candles.iloc[i], None)
    assert resumed.operating.equity == pytest.approx(ref.operating.equity)
    assert resumed.control.equity == pytest.approx(ref.control.equity)
    assert len(resumed.intents) == len(ref.intents) == 1
    assert resumed.operating.exits == ref.operating.exits == 1


def test_engine_parity_batch_vs_incremental():
    rows = [bar(0, 100, 100, 100, 100),
            bar(1, 99, 101, 98, 100),
            bar(2, 100, 112, 99, 111),
            bar(3, 111, 121, 110, 120),
            bar(4, 120, 121, 119, 120),
            bar(5, 120, 121, 119, 120),
            bar(6, 119, 125, 118, 124),
            bar(7, 124, 126, 123, 125),
            bar(8, 125, 126, 124, 125)]
    candles = frame(rows)
    sig = pd.DataFrame([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                         "stop_loss": 90.0, "take_profit_1": 110.0,
                         "take_profit_2": 120.0, "holding_bars": 6,
                         "leverage": 1.0}])
    res, trades = bt_engine.run_backtest(
        candles, sig, initial_equity=100.0, costs=bt_engine.CostModel(),
        execution=bt_engine.ExecutionConfig(entry_expiry_bars=12,
                                            max_holding_bars=2016,
                                            tp1_fraction=0.5, leverage=1.0,
                                            max_leverage=1.0))
    ac = account()
    ac.on_bar_close(0, candles.iloc[0])
    ac.arm_pending({**long_signal(holding=6), "signal_bar": 0})
    for i in range(1, len(candles)):
        ac.on_bar_close(i, candles.iloc[i], n_bars=len(candles))
    assert len(trades) == ac.exits == 1
    assert ac.equity == pytest.approx(res.final_equity, rel=1e-9)
    got = ac.events[0]
    assert got["reason"] == trades[0].exit_reason == "tp2"
    assert got["fees"] == pytest.approx(trades[0].fees, rel=1e-9)
    assert got["funding"] == pytest.approx(trades[0].funding, rel=1e-9)
    assert got["gross"] == pytest.approx(trades[0].gross_pnl, rel=1e-9)


def test_funding_parity_at_funding_bar():
    base8 = int(pd.Timestamp("2023-01-02 07:55", tz="UTC").value // 10 ** 6)
    rows = [bar(0, 100, 100, 100, 100, base_ms=base8),
            bar(1, 99, 101, 98, 100, base_ms=base8),   # entry
            bar(2, 100, 101, 99, 100, base_ms=base8),  # 08:00-ish open? no: use explicit
            bar(3, 100, 101, 99, 100, base_ms=base8)]
    # Force bar2 to be exactly the 08:00 funding boundary.
    rows[2]["open_time"] = pd.Timestamp("2023-01-02 08:00", tz="UTC")
    rows[2]["close_time"] = pd.Timestamp("2023-01-02 08:04:59.999", tz="UTC")
    candles = frame(rows)
    sig = pd.DataFrame([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                         "stop_loss": 50.0, "take_profit_1": 500.0,
                         "take_profit_2": 600.0, "holding_bars": 2,
                         "leverage": 1.0}])
    res, trades = bt_engine.run_backtest(
        candles, sig, initial_equity=100.0, costs=bt_engine.CostModel(),
        execution=bt_engine.ExecutionConfig(entry_expiry_bars=12,
                                            max_holding_bars=2016,
                                            tp1_fraction=0.5, leverage=1.0,
                                            max_leverage=1.0))
    ac = account()
    ac.on_bar_close(0, candles.iloc[0])
    ac.arm_pending({**long_signal(sl=50.0, tp1=500.0, tp2=600.0, holding=2),
                      "signal_bar": 0})
    for i in range(1, len(candles)):
        ac.on_bar_close(i, candles.iloc[i], n_bars=99)
    assert trades[0].funding > 0
    assert ac.events[0]["funding"] == pytest.approx(trades[0].funding, rel=1e-9)


# ------------------------------------------------- control causality ---
def test_control_reference_is_past_only():
    trip = fx.ControlDivergenceTrip(0.05, 100.0)
    trip.post_control_equity(5, 105.0)
    trip.post_control_equity(10, 110.0)
    assert trip.expected_at(7) == pytest.approx(105.0)
    assert trip.expected_at(4) == pytest.approx(100.0)
    trip.post_control_equity(20, 200.0)  # future info arrives later...
    assert trip.expected_at(7) == pytest.approx(105.0)  # ...never leaks into the past
    assert trip.expected_at(20) == pytest.approx(200.0)
    with pytest.raises(AssertionError):
        trip.post_control_equity(20, 201.0)  # non-advancing trace refused


def test_under_only_trip_vs_control():
    trip = fx.ControlDivergenceTrip(0.05, 100.0)
    for b in range(5):
        trip.post_control_equity(b, 100.0)
    assert trip.check(4, 106.0, "t") is None  # overperformance: info only
    assert trip.tripped is False
    ev = trip.check(4, 94.9, "t")
    assert ev is not None and ev["status"] == "TRIPPED_NOW"
    assert ev["direction"] == "UNDER"
    assert trip.check(4, 100.0, "t")["status"] == "BLOCKED_LATCHED"
    snap = trip.snapshot()
    assert "control_trace" in snap and "n_curve_points" not in snap
    trip2 = fx.ControlDivergenceTrip(0.05, 100.0)
    trip2.restore(json.loads(json.dumps(snap)))
    assert trip2.expected_at(4) == pytest.approx(100.0) and trip2.tripped is True


def test_guard_never_sees_future_in_strategy():
    cfg = copy.deepcopy(CONFIG)
    cfg["decision_clock"]["stride_bars"] = 1
    st = fx.FeedExecStrategy(cfg, n_bars=4)
    candles = frame([bar(0, 100, 100, 100, 100),
                     bar(1, 99, 101, 98, 100),
                     bar(2, 100, 101, 99, 100),
                     bar(3, 100, 101, 99, 100)])
    for i in range(len(candles)):
        st.on_bar(i, candles.iloc[i], None)
        assert st.trip.expected_at(i) == pytest.approx(st.control.equity)
    assert st.trip.tripped is False


# ----------------------------------------------- alerts + exactly-once ---
def test_deterministic_alert_ids_and_exactly_once():
    cfg = copy.deepcopy(CONFIG)
    st = fx.FeedExecStrategy(cfg, n_bars=4)
    a1 = st.emit_alert({"kind": "DAILY_LOSS_HALT", "bar_idx": 3,
                        "bar_time": "t", "equity_now": 96.0})
    a2 = st.emit_alert({"kind": "DAILY_LOSS_HALT", "bar_idx": 3,
                        "bar_time": "t", "equity_now": 96.0})
    assert a1["alert_id"] == a2["alert_id"] and a1["alert_id"].startswith("r76-")
    assert len(st.alerts) == 1
    b = fx.FeedExecStrategy(cfg, n_bars=4)
    c = b.emit_alert({"kind": "DAILY_LOSS_HALT", "bar_idx": 3,
                      "bar_time": "t", "equity_now": 96.0})
    assert c["alert_id"] == a1["alert_id"]


def test_strategy_skips_off_clock_decisions():
    cfg = copy.deepcopy(CONFIG)
    cfg["decision_clock"]["stride_bars"] = 12
    st = fx.FeedExecStrategy(cfg, n_bars=14)
    candles = frame([bar(i, 100, 101, 99, 100) for i in range(14)])
    sig = long_signal()
    dec = {"action": "LONG", "confidence": 1.0, "entry_limit": sig["entry_limit"],
           "stop_loss": sig["stop_loss"], "take_profit_1": sig["take_profit_1"],
           "take_profit_2": sig["take_profit_2"], "holding_bars": sig["holding_bars"]}
    for i in range(len(candles)):
        st.on_bar(i, candles.iloc[i], dec if i == 5 else None)
    assert st.skipped_clock == 1 and st.signals_seen == 0 and len(st.intents) == 0
