"""oc_paperrecon tests: causality/truncation + hand-checked synthetic cases.

Covers the replay helpers in research/diagnostics/oc_paperrecon/replay_paper.py
(strict trade-through, placement-minute causality, dip 16-min gate, stop-first,
market next-bar-open, gate costs). No network, no artifacts reads.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "diagnostics" / "oc_paperrecon"))

from replay_paper import (  # noqa: E402
    MAKER,
    TAKER,
    dip_pid_info,
    engine_exit,
    first_buy_through,
    first_sell_through,
    first_stop_hit,
    reconstruct_orders,
    walk_money,
)


def bars(*rows):
    return [{"t": t, "o": o, "h": h, "l": ll, "c": c} for t, o, h, ll, c in rows]


def test_placement_minute_never_fills_causality():
    b = bars((1000, 10, 11, 9, 10))  # low 9 < limit 10, but same minute
    assert first_buy_through(10, 1000, b) is None
    assert first_sell_through(9, 1000, b) is None
    assert first_stop_hit(9, 1000, b) is None
    # next minute fills
    b2 = b + [{"t": 2000, "o": 10, "h": 11, "l": 9, "c": 10}]
    assert first_buy_through(10, 1000, b2)["t"] == 2000


def test_strict_trade_through_hand_checked():
    # Buy: low == price is NOT a fill (mirrors BNB TP 767.4 vs high 767.4).
    b = bars((2000, 10, 10.5, 10.0, 10.2))
    assert first_buy_through(10.0, 1000, b) is None
    b2 = bars((2000, 10, 10.5, 9.99, 10.2))
    assert first_buy_through(10.0, 1000, b2)["t"] == 2000
    # Sell: high == price is NOT a fill.
    assert first_sell_through(10.5, 1000, b) is None
    assert first_sell_through(10.4, 1000, b)["t"] == 2000
    # Stop long: low == trigger IS a hit (paper.py: l <= trigger).
    assert first_stop_hit(10.0, 1000, b)["t"] == 2000


def test_dip_16min_gate_truncation():
    pid = "d3BTC25hrwmc"  # holding bar decoded from base36 suffix
    info = dip_pid_info(pid)
    assert info is not None and info["phase"] == 3 and info["coin"] == "BTC"
    gate = info["bar_start_ms"] + 16 * 60_000
    touch = [{"t": gate - 60_000, "o": 100, "h": 100, "l": 90, "c": 95}]
    assert first_buy_through(95, gate - 120_000, touch, gate) is None
    after = touch + [{"t": gate, "o": 95, "h": 96, "l": 94, "c": 95}]
    assert first_buy_through(95, gate - 120_000, after, gate)["t"] == gate
    # life_end truncation: bars past cancellation are ignored
    assert first_buy_through(95, gate - 120_000, after, gate, end_ms=gate - 1) is None


def test_stop_first_same_bar_hand_checked():
    # TP 110 touched (h=111) and stop 90 triggered (l=89) in the same bar:
    # stop wins at min(trigger, open).
    b = bars((2000, 100, 111, 89, 100))
    out = engine_exit(110, 90, 1000, None, b)
    assert out["kind"] == "stop" and out["bar_ms"] == 2000
    assert out["px"] == 90 and out["fee"] == TAKER
    # TP alone: maker at the TP.
    b2 = bars((2000, 100, 111, 95, 100))
    out2 = engine_exit(110, 90, 1000, None, b2)
    assert (out2["kind"], out2["px"], out2["fee"]) == ("tp", 110, MAKER)
    # BNB near-miss regression: high == TP -> no TP, nothing else -> None.
    b3 = bars((1791340500000, 766.7, 767.4, 766.7, 767.3))
    out3 = engine_exit(767.4, 710.5, 1791338520000, None, b3)
    assert out3["kind"] is None


def test_market_exit_next_bar_open():
    b = bars((1000, 50, 51, 49, 50), (2000, 52, 53, 51, 52), (3000, 54, 55, 53, 54))
    out = engine_exit(None, None, 0, 1500, b)
    assert (out["kind"], out["bar_ms"], out["px"], out["fee"]) == ("market", 2000, 52, TAKER)
    # resting TP earlier than the market send wins.
    b2 = bars((1000, 50, 60, 49, 55), (2000, 52, 53, 51, 52))
    out2 = engine_exit(55, None, 0, 1500, b2)
    assert out2["kind"] == "tp" and out2["bar_ms"] == 1000


def test_reconstruct_market_exit_synthesis():
    acts = [
        {"t": "2026-10-07 02:01:00+00:00", "op": "place",
         "payload": {"symbol": "BTCUSDT", "side": "Buy", "qty": "0.001",
                     "orderLinkId": "d0BTC25hrwo0E", "orderType": "Limit",
                     "price": "83859.5", "timeInForce": "GTC"}},
        {"t": "2026-10-07 02:02:11+00:00", "op": "fill", "link": "d0BTC25hrwo0E",
         "qty": "0.001", "price": "83859.5"},
        {"t": "2026-10-07 04:00:01+00:00", "op": "market_exit", "piece": "d0BTC25hrwo0",
         "reason": "time_exit",
         "payload": {"symbol": "BTCUSDT", "side": "Sell", "orderType": "Market",
                     "qty": "0.001", "reduceOnly": True,
                     "orderLinkId": "d0BTC25hrwo0Xabc", "positionIdx": 1}},
        {"t": "2026-10-07 04:01:20+00:00", "op": "fill", "link": "d0BTC25hrwo0Xabc",
         "qty": "0.001", "price": "84200.0"},
    ]
    orders = reconstruct_orders(acts)
    x = orders[("d0BTC25hrwo0Xabc", "2026-10-07 04:00:01+00:00")]
    assert x["otype"] == "Market" and x["origin"] == "mex"
    assert x["fill_t"] == "2026-10-07 04:01:20+00:00" and x["fill_price"] == 84200.0


def test_walk_money_gate_costs_hand_checked():
    # Long 1 @100 (maker), exit @110 (taker); funding settlement on 1.0 held.
    evts = [{"bar": 1000, "link": "pE", "symbol": "S", "qty": 1.0, "px": 100.0,
             "fee": MAKER, "entry": True},
            {"bar": 2000, "link": "pX", "symbol": "S", "qty": 1.0, "px": 110.0,
             "fee": TAKER, "entry": False}]
    cash, fees, funding, rl = walk_money(evts, [(3000, "S", 110.0)])
    assert rl == 10.0
    assert fees == 100 * MAKER + 110 * TAKER
    assert funding == 0.0  # flat at settlement
    assert cash == 5000 + 10.0 - fees
    # held through settlement: funding charged on notional at bar open.
    evts2 = [dict(evts[0])]
    cash2, _, funding2, _ = walk_money(evts2, [(3000, "S", 110.0)])
    assert funding2 == 0.0001 * 1.0 * 110.0
    assert cash2 == 5000 - 100 * MAKER - funding2
