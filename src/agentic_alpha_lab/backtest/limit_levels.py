"""1-minute event-driven backtest for limit orders resting at price levels (ma-sr program).

Orders are created at a decision time (a closed bar of the signal timeframe) with a
limit price computed from data known at that time. From the next minute on:
- a buy limit fills only when a 1m low trades strictly below the limit (trade-through);
  a sell limit when a 1m high trades strictly above it (no queue assumption);
- after the fill minute, exits are checked minute by minute: stop first, then target;
  the fill minute itself is not used for exits (its intraminute order is unknown);
- unfilled orders expire; open trades time out at the close of the last allowed minute.
One position at a time; new orders are ignored while an order or position is active.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LimitCosts:
    maker: float = 0.0002
    taker: float = 0.0005
    stop_slippage: float = 0.0002


@dataclass
class Order:
    t_decision: pd.Timestamp  # decision bar close time (order becomes live the next minute)
    side: int
    limit: float
    stop: float
    target: float
    expiry_min: int
    max_hold_min: int
    size: float = 1.0


def run_orders(m1: pd.DataFrame, orders: list[Order], costs: LimitCosts = LimitCosts()) -> dict:
    t = m1["open_time"].dt.tz_convert(None).to_numpy()  # naive UTC datetime64 for fast comparisons
    op, lo, hi, cl = (m1[k].to_numpy(float) for k in ("open", "low", "high", "close"))
    equity = 100.0
    trades = []
    busy_until = np.datetime64("1970-01-01")
    curve_t, curve_eq = [], []
    for od in sorted(orders, key=lambda o: o.t_decision):
        start = np.datetime64(od.t_decision.tz_convert(None)) + np.timedelta64(1, "ms")
        if start <= busy_until:
            continue
        i0 = int(np.searchsorted(t, start))
        i_exp = min(i0 + od.expiry_min, len(t))
        fill = None
        for i in range(i0, i_exp):
            if (od.side > 0 and lo[i] < od.limit) or (od.side < 0 and hi[i] > od.limit):
                fill = i
                break
        if fill is None:
            busy_until = t[i_exp - 1] if i_exp > i0 else busy_until
            continue
        qty = od.size * equity / od.limit
        fee_in = costs.maker * qty * od.limit
        exit_px, kind, j_exit = None, "timeout", min(fill + od.max_hold_min, len(t) - 1)
        for j in range(fill + 1, j_exit + 1):
            if od.side > 0:
                if lo[j] <= od.stop:
                    exit_px, kind = min(od.stop, op[j]) * (1 - costs.stop_slippage), "stop"  # gap through stop fills at the open
                elif hi[j] > od.target:
                    exit_px, kind = od.target, "target"
            else:
                if hi[j] >= od.stop:
                    exit_px, kind = max(od.stop, op[j]) * (1 + costs.stop_slippage), "stop"
                elif lo[j] < od.target:
                    exit_px, kind = od.target, "target"
            if exit_px is not None:
                j_exit = j
                break
        if exit_px is None:
            exit_px = cl[j_exit] * (1 - costs.stop_slippage * od.side)
        fee_out = (costs.maker if kind == "target" else costs.taker) * qty * exit_px
        pnl = od.side * qty * (exit_px - od.limit) - fee_in - fee_out
        equity += pnl
        trades.append(dict(t_fill=pd.Timestamp(t[fill], tz="UTC"), t_exit=pd.Timestamp(t[j_exit], tz="UTC"), side=od.side,
                           entry=od.limit, exit=exit_px, kind=kind, pnl=pnl, ret=pnl / (equity - pnl)))
        curve_t.append(t[j_exit])
        curve_eq.append(equity)
        busy_until = t[j_exit]
    return dict(equity=equity, trades=pd.DataFrame(trades), curve=pd.Series(curve_eq, index=pd.DatetimeIndex(curve_t, tz="UTC")))


def summarize_trades(res: dict, days: float) -> dict:
    tr = res["trades"]
    if len(tr) == 0:
        return dict(net_pct=0.0, trades=0)
    eq = np.concatenate([[100.0], res["curve"].to_numpy()])
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    g = res["equity"] / 100
    return dict(net_pct=100 * (g - 1), monthly_geo_pct=100 * (g ** (30.4375 / days) - 1) if g > 0 else -100.0, trades=len(tr),
                per_day=len(tr) / days, win_rate=float((tr.pnl > 0).mean()), mean_ret_bps=1e4 * float(tr.ret.mean()),
                dd_trade_close_pct=100 * dd, stop_rate=float((tr.kind == "stop").mean()), target_rate=float((tr.kind == "target").mean()))
