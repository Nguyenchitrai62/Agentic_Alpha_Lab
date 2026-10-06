"""Unit tests for the oc_tsmom bot sleeve (bot/tsmom.py). Pure, no network."""
import math

import pandas as pd

from bot import mirror
from bot import tsmom

DAY = pd.Timestamp("2026-01-05 00:00", tz="UTC")
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
        "ETHUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.01")}


def _trend(n=40, start=100.0, drift=0.01):
    return [start * math.exp(drift * i) for i in range(n)]


def test_signal_sign_up_down_flat():
    up = {"BTCUSDT": _trend(drift=0.01), "ETHUSDT": _trend(drift=-0.01)}
    assert tsmom.signal(up) == {"BTCUSDT": 1, "ETHUSDT": -1}
    flat = {"BTCUSDT": [100.0] * 40}
    assert tsmom.signal(flat) == {"BTCUSDT": 0}  # zero 30d return -> flat
    short = {"BTCUSDT": [100.0] * 10}
    assert tsmom.signal(short) == {"BTCUSDT": 0}  # < 31 closes -> flat
    nan = {"BTCUSDT": [100.0] * 30 + [float("nan")]}
    assert tsmom.signal(nan) == {"BTCUSDT": 0}
    # DataFrame input (research shape): last-31-row rule
    df = pd.DataFrame({"BTCUSDT": _trend(n=45, drift=0.005)},
                      index=pd.date_range("2025-01-01", periods=45, tz="UTC"))
    assert tsmom.signal(df) == {"BTCUSDT": 1}


def test_target_weights_vol_scaling_and_caps():
    w = tsmom.target_weights({"BTCUSDT": 1}, {"BTCUSDT": 0.5})
    assert w["BTCUSDT"] == abs(w["BTCUSDT"]) and w["BTCUSDT"] == 0.10 / 0.5 * 0.25
    tiny_vol = tsmom.target_weights({"BTCUSDT": 1}, {"BTCUSDT": 0.01})  # raw 10 -> cap 1.0
    assert tiny_vol["BTCUSDT"] == 0.25
    assert tsmom.target_weights({"BTCUSDT": 0}, {"BTCUSDT": 0.2})["BTCUSDT"] == 0.0
    assert tsmom.target_weights({"BTCUSDT": 1}, {"BTCUSDT": 0.0})["BTCUSDT"] == 0.0
    assert tsmom.target_weights({"BTCUSDT": -1}, {"BTCUSDT": float("nan")})["BTCUSDT"] == 0.0
    custom = tsmom.target_weights({"BTCUSDT": 1}, {"BTCUSDT": 0.4}, vol_target=0.10, cap=0.5, sleeve_weight=1.0)
    assert abs(custom["BTCUSDT"] - min(0.10 / 0.4, 0.5)) < 1e-12


def test_orders_limit_price_window_and_single_per_coin():
    tg = {"BTCUSDT": 0.10}
    got = tsmom.orders(tg, {}, {"BTCUSDT": 100000.0}, 10000.0, DAY,
                       atr={"BTCUSDT": 1000.0}, instruments=INST)
    kinds = {o.kind for o in got}
    assert kinds == {"entry", "stop"}  # no take-profit by default (trend sleeve)
    entry = next(o for o in got if o.kind == "entry")
    assert entry.side == "Buy" and entry.position_idx == 1 and not entry.reduce_only
    assert entry.price < 100000.0 and abs(entry.price / 99950.0 - 1) < 1e-9  # 5 bps below
    assert entry.meta["valid_until"] == str(DAY + pd.Timedelta(hours=23, minutes=55))
    assert entry.meta["placed_from"] == str(DAY + pd.Timedelta(minutes=5))
    assert abs(entry.qty - 0.10 * 10000 / 100000.0) < 1e-9
    # sell side mirrors above the open on the hedge short side
    got_s = tsmom.orders({"ETHUSDT": -0.10}, {}, {"ETHUSDT": 3000.0}, 10000.0, DAY,
                         atr={"ETHUSDT": 60.0}, instruments=INST)
    entry_s = next(o for o in got_s if o.kind == "entry")
    assert entry_s.side == "Sell" and entry_s.position_idx == 2 and entry_s.price > 3000.0


def test_orders_stop_attached_and_optional_tp():
    got = tsmom.orders({"BTCUSDT": 0.10}, {}, {"BTCUSDT": 100000.0}, 10000.0, DAY,
                       atr={"BTCUSDT": 1000.0}, instruments=INST)
    (stop,) = [o for o in got if o.kind == "stop"]
    assert stop.side == "Sell" and stop.reduce_only and stop.trigger == 100000.0 - 3 * 1000.0
    assert isinstance(stop, mirror.Order)
    short = tsmom.orders({"BTCUSDT": -0.10}, {}, {"BTCUSDT": 100000.0}, 10000.0, DAY,
                         atr={"BTCUSDT": 1000.0}, instruments=INST)
    (stop_sh,) = [o for o in short if o.kind == "stop"]
    assert stop_sh.side == "Buy" and stop_sh.trigger == 100000.0 + 3 * 1000.0
    with_tp = tsmom.orders({"BTCUSDT": 0.10}, {}, {"BTCUSDT": 100000.0}, 10000.0, DAY,
                           atr={"BTCUSDT": 1000.0}, instruments=INST, tp_mult=6.0)
    (tp,) = [o for o in with_tp if o.kind == "tp"]
    assert tp.price == 100000.0 + 6 * 1000.0 and tp.reduce_only


def test_orders_reduce_only_when_shrinking():
    # long 0.02 BTC, target halves it -> reduce-only limit, kind reduce
    shrink = tsmom.orders({"BTCUSDT": 0.05}, {"BTCUSDT": 0.02}, {"BTCUSDT": 100000.0},
                          10000.0, DAY, atr={"BTCUSDT": 1000.0}, instruments=INST)
    (entry,) = [o for o in shrink if o.kind in ("entry", "reduce")]
    assert entry.kind == "reduce" and entry.reduce_only and entry.side == "Sell"
    # growing the same long -> fresh entry, not reduce-only
    grow = tsmom.orders({"BTCUSDT": 0.20}, {"BTCUSDT": 0.005}, {"BTCUSDT": 100000.0},
                        10000.0, DAY, atr={"BTCUSDT": 1000.0}, instruments=INST)
    (entry_g,) = [o for o in grow if o.kind in ("entry", "reduce")]
    assert entry_g.kind == "entry" and not entry_g.reduce_only and entry_g.side == "Buy"
    # flatten to zero -> reduce-only close, no stop (nothing new to protect)
    flat = tsmom.orders({"BTCUSDT": 0.0}, {"BTCUSDT": 0.01}, {"BTCUSDT": 100000.0},
                        10000.0, DAY, atr={"BTCUSDT": 1000.0}, instruments=INST)
    assert [o.kind for o in flat] == ["reduce"] and flat[0].reduce_only


def test_orders_skip_dust_below_min_notional_and_rounding():
    # delta 0.00001 BTC x 100000 = 1 USDT < 5 minimum -> no order at all
    assert tsmom.orders({"BTCUSDT": 0.0001}, {}, {"BTCUSDT": 100000.0}, 10000.0, DAY,
                        atr={"BTCUSDT": 1000.0}, instruments=INST) == []
    # exchange-unit rounding: qty down to the step, price to the tick
    got = tsmom.orders({"BTCUSDT": 0.10}, {}, {"BTCUSDT": 100000.06}, 10000.0, DAY,
                       atr={"BTCUSDT": 1000.0}, instruments=INST)
    entry = next(o for o in got if o.kind == "entry")
    assert entry.qty == 0.009 and entry.price == 99950.0  # qty floored to step, buy limit below open
