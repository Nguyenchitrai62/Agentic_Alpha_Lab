import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.limit_levels import LimitCosts, Order, run_orders


def _m1(prices):
    t = pd.date_range("2024-01-01", periods=len(prices), freq="1min", tz="UTC")
    o, h, l, c = zip(*prices)
    return pd.DataFrame({"open_time": t, "open": o, "high": h, "low": l, "close": c})


def test_touch_without_trade_through_does_not_fill():
    m = _m1([(100, 100, 100, 100), (100, 101, 99.0, 100), (100, 101, 99.5, 100)])
    od = Order(m.open_time[0] + pd.Timedelta("59s"), 1, 99.0, 98, 102, expiry_min=5, max_hold_min=5)
    assert len(run_orders(m, [od], LimitCosts(0, 0, 0))["trades"]) == 0


def test_fill_then_stop_first_and_gap_fills_at_open():
    m = _m1([(100, 100, 100, 100), (100, 100, 98.9, 99.5), (99.5, 103, 97.0, 99), (96.0, 96, 95, 95.5)])
    od = Order(m.open_time[0] + pd.Timedelta("59s"), 1, 99.0, 97.5, 102.5, expiry_min=5, max_hold_min=10)
    tr = run_orders(m, [od], LimitCosts(0, 0, 0))["trades"]
    assert tr.kind.iloc[0] == "stop" and np.isclose(tr.exit.iloc[0], 97.5)  # both hit in minute 2 -> stop first
    od2 = Order(m.open_time[0] + pd.Timedelta("59s"), 1, 99.0, 96.5, 110, expiry_min=5, max_hold_min=10)
    tr2 = run_orders(m, [od2], LimitCosts(0, 0, 0))["trades"]
    assert tr2.kind.iloc[0] == "stop" and np.isclose(tr2.exit.iloc[0], 96.0)  # gap below stop fills at open


def test_order_not_live_before_decision_minute_passes():
    m = _m1([(100, 100, 90, 100), (100, 100, 100, 100), (100, 100, 100, 100)])
    od = Order(m.open_time[0] + pd.Timedelta("59s"), 1, 99.0, 97, 102, expiry_min=2, max_hold_min=5)
    assert len(run_orders(m, [od], LimitCosts(0, 0, 0))["trades"]) == 0
