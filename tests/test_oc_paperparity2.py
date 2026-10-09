"""oc_paperparity2 tests: causality + hand-checked synthetic fill/exit cases."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "diagnostics" / "oc_paperparity2"))

from check_parity2 import (
    dip_pid_info,
    expected_limit_buy_fill,
    expected_stop_trigger,
    expected_tp_sell_fill,
    reconstruct_orders,
    resolve_exit_bar,
)


def _b(t_min, o=100.0, h=100.0, l=100.0, c=100.0):
    return {"t": t_min, "o": o, "h": h, "l": l, "c": c}


def test_causality_placement_minute_never_fills():
    # Even with a deep trade-through, the placement minute itself never fills
    # (both the engine and bot/paper.py require bar_start > placement).
    bars = [_b(1_000, l=90.0), _b(1_060, l=90.0)]
    assert expected_limit_buy_fill(95.0, 1_000, bars) == 1_060
    assert expected_limit_buy_fill(95.0, 1_060, bars) is None
    assert expected_tp_sell_fill(99.0, 1_000, bars) == 1_060
    assert expected_stop_trigger(99.0, 1_000, [_b(1_000, l=80.0)]) is None


def test_minute16_gate_and_truncation():
    # Engine minute>=16: bars before holding-bar+16min never fill.
    bars = [_b(2_000, l=90.0), _b(3_000, l=90.0)]
    assert expected_limit_buy_fill(95.0, 1_000, bars, bar_min_ms=2_500) == 3_000
    # truncation: bars past cancel/expiry must not count (caller slices scope)
    assert expected_limit_buy_fill(95.0, 1_000, [_b(2_000, l=90.0)]) == 2_000


def test_hand_checked_synthetic_fill_and_stop_first():
    # Hand-checked tape: Buy limit 100.
    # bar1 trades at/above (low == price is NOT a strict trade-through).
    # bar2 pierces (low < price) -> fill. TP 101 hit bar3; SL 99 hit bar3 too
    # -> stop-first wins.
    bars = [_b(10_000, o=100.5, h=101.0, l=100.0, c=100.5),
            _b(10_060, o=100.5, h=100.6, l=99.5, c=100.0),
            _b(10_120, o=100.0, h=102.0, l=98.0, c=101.0)]
    assert expected_limit_buy_fill(100.0, 9_000, bars) == 10_060
    sl = expected_stop_trigger(99.0, 10_060, bars)
    tp = expected_tp_sell_fill(101.0, 10_060, bars)
    assert (sl, tp) == (10_120, 10_120)
    kind, bar = resolve_exit_bar(sl, tp)
    assert (kind, bar) == ("stop", 10_120)
    # TP-only tape resolves to tp.
    kind2, bar2 = resolve_exit_bar(None, 10_120)
    assert (kind2, bar2) == ("tp", 10_120)
    assert resolve_exit_bar(None, None) == (None, None)


def test_pid_parsing_known_bars():
    # Known piece ids decode to their holding-bar starts (4h grids).
    assert dip_pid_info("d1BNB25hrx9o")["bar_start_ms"] == 1791378000000  # 13:00Z
    assert dip_pid_info("d1BNB25hrx9o")["rung"] == 2.5
    assert dip_pid_info("d3ETH50hrx6c")["rung10"] == 50
    assert dip_pid_info("b0ETHhrvdc") is None  # book pids are not dip pids


def test_postonly_reject_never_rests():
    acts = [
        {"t": "2026-10-07 02:02:13.352055+00:00", "op": "place",
         "payload": {"symbol": "BNBUSDT", "side": "Buy", "qty": "0.01",
                     "orderLinkId": "d1BNB25hrwpoE", "orderType": "Limit",
                     "price": "762.9", "timeInForce": "PostOnly"}},
        {"t": "2026-10-07 02:02:13.352055+00:00", "op": "postonly_reject",
         "link": "d1BNB25hrwpoE", "symbol": "BNBUSDT", "price": "762.9"},
    ]
    orders = reconstruct_orders(acts)
    key = ("d1BNB25hrwpoE", "2026-10-07 02:02:13.352055+00:00")
    assert orders[key]["rejected"] is True
