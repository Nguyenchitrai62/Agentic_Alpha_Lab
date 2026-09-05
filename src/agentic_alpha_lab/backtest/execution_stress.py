"""Versioned OHLC execution sensitivity, fixed/reduced exposure <=1x only.

Preserves the frozen ohlc-v2 engine. This is not an exchange queue/mark simulator.
The adverse-price drawdown samples possible pre-TP lows/highs and prior closes;
it is neither true intrabar maximum drawdown nor a guaranteed conservative bound.
"""
from dataclasses import asdict, dataclass
import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import (
    CostModel, ExecutionConfig, Trade, BacktestResult, _entry_fill, _stop_fill,
    _take_profit_fill, _is_funding_time, _max_drawdown,
)


@dataclass(frozen=True)
class FillStress:
    entry_penetration_bps: float = 0.0
    target_penetration_bps: float = 0.0
    market_exit_slippage_bps: float = 0.0
    market_exit_fee_rate: float | None = None
    allow_limit_price_improvement: bool = True

    def validate(self):
        values = [self.entry_penetration_bps, self.target_penetration_bps, self.market_exit_slippage_bps]
        if not all(np.isfinite(x) and 0 <= x < 1000 for x in values):
            raise ValueError("Invalid stress basis points")
        if self.market_exit_fee_rate is not None and not 0 <= self.market_exit_fee_rate < 1:
            raise ValueError("Invalid market exit fee")


def entry_fill(bar, side, price, stress):
    crossed = float(bar.low) <= price * (1 - stress.entry_penetration_bps / 10000) if side == 1 else float(bar.high) >= price * (1 + stress.entry_penetration_bps / 10000)
    if not crossed:
        return None
    fill = _entry_fill(bar, side, price)
    return fill if stress.allow_limit_price_improvement else price


def target_fill(bar, side, price, stress):
    crossed = float(bar.high) >= price * (1 + stress.target_penetration_bps / 10000) if side == 1 else float(bar.low) <= price * (1 - stress.target_penetration_bps / 10000)
    if not crossed:
        return None
    fill = _take_profit_fill(bar, side, price)
    return fill if stress.allow_limit_price_improvement else price


def run_stress(candles, signals, initial_equity=100., costs=None, execution=None, stress=None):
    costs, execution, stress = costs or CostModel(), execution or ExecutionConfig(), stress or FillStress()
    stress.validate()
    if not (0 < execution.leverage <= execution.max_leverage <= 1):
        raise ValueError("Stress simulator supports exposure <=1x only; no liquidation model")
    if initial_equity <= 0 or not 0 < execution.tp1_fraction < 1 or execution.intrabar_policy != "stop_first":
        raise ValueError("Invalid equity, TP fraction or intrabar policy")
    if execution.entry_expiry_bars < 1 or execution.max_holding_bars < 1:
        raise ValueError("Invalid execution horizon")
    if costs.funding_interval_hours < 1 or 24 % costs.funding_interval_hours:
        raise ValueError("Funding interval must divide 24")
    frame = candles.sort_values("open_time").reset_index(drop=True)
    signals = signals.sort_values("bar_index").reset_index(drop=True)
    equity, available, rejected = float(initial_equity), 0, 0
    curve, adverse_curve, trades = [equity], [equity], []
    exit_fee_rate = costs.fee_rate_per_fill if stress.market_exit_fee_rate is None else stress.market_exit_fee_rate
    for signal in signals.itertuples(index=False):
        if equity <= 0:
            break
        index, side = int(signal.bar_index), int(signal.direction)
        if side not in (-1, 1) or index < available:
            rejected += 1
            continue
        if index < 0 or index >= len(frame):
            raise ValueError("Signal index outside source")
        hold = int(getattr(signal, "holding_bars", execution.max_holding_bars))
        if not 1 <= hold <= execution.max_holding_bars:
            raise ValueError("Holding horizon outside cap")
        requested = float(getattr(signal, "leverage", execution.leverage))
        if not np.isfinite(requested) or requested <= 0 or requested > 1:
            raise ValueError("Signal exposure must be positive and <=1x")
        leverage = min(max(requested, execution.leverage), execution.max_leverage)
        entry_index, price = None, None
        for j in range(index + 1, min(index + execution.entry_expiry_bars + 1, len(frame))):
            fill = entry_fill(frame.iloc[j], side, float(signal.entry_limit), stress)
            if fill is not None:
                entry_index, price = j, fill
                break
        if entry_index is None or entry_index + hold >= len(frame):
            rejected += 1
            continue
        before, notional = equity, equity * leverage
        fees, funding, gross, remaining = notional * costs.fee_rate_per_fill, 0., 0., 1.
        equity -= fees
        curve.append(equity)
        adverse_curve.append(equity)
        tp1_done, exit_reason, end = False, "time", entry_index + hold

        def close_fraction(fill, fraction, rate):
            nonlocal equity, fees, gross, remaining
            pnl = side * (fill / price - 1) * notional * fraction
            charge = notional * fraction * fill / price * rate
            gross += pnl
            fees += charge
            equity += pnl - charge
            remaining -= fraction

        for j in range(entry_index, end):
            bar = frame.iloc[j]
            if j > entry_index and _is_funding_time(pd.Timestamp(bar.open_time), costs.funding_interval_hours):
                rate = costs.funding_long_rate if side == 1 else costs.funding_short_rate
                charge = notional / price * float(bar.open) * remaining * rate
                funding += charge
                equity -= charge
            stop = _stop_fill(bar, side, float(signal.stop_loss))
            if stop is not None:
                fill = stop * (1 - side * stress.market_exit_slippage_bps / 10000)
                close_fraction(fill, remaining, exit_fee_rate)
                exit_reason, end = "stop", j
                curve.append(equity)
                adverse_curve.append(equity)
                break
            adverse = float(bar.low if side == 1 else bar.high)
            adverse_curve.append(max(0., equity + side * (adverse / price - 1) * notional * remaining))
            opened_fill = (side == 1 and float(bar.open) <= float(signal.entry_limit)) or (side == -1 and float(bar.open) >= float(signal.entry_limit))
            allow_targets = j != entry_index or opened_fill
            if allow_targets:
                if not tp1_done:
                    fill = target_fill(bar, side, float(signal.take_profit_1), stress)
                    if fill is not None:
                        close_fraction(fill, execution.tp1_fraction, costs.fee_rate_per_fill)
                        tp1_done = True
                fill = target_fill(bar, side, float(signal.take_profit_2), stress)
                if remaining > 0 and fill is not None:
                    close_fraction(fill, remaining, costs.fee_rate_per_fill)
                    exit_reason, end = "tp2", j
                    curve.append(equity)
                    adverse_curve.append(equity)
                    break
            mark_equity = max(0., equity + side * (float(bar.close) / price - 1) * notional * remaining)
            curve.append(mark_equity)
            adverse_curve.append(mark_equity)
        if remaining > 0:
            bar = frame.iloc[end]
            if _is_funding_time(pd.Timestamp(bar.open_time), costs.funding_interval_hours):
                rate = costs.funding_long_rate if side == 1 else costs.funding_short_rate
                charge = notional / price * float(bar.open) * remaining * rate
                funding += charge
                equity -= charge
            fill = float(bar.open) * (1 - side * stress.market_exit_slippage_bps / 10000)
            close_fraction(fill, remaining, exit_fee_rate)
            exit_reason = "time_after_tp1" if tp1_done else "time"
            curve.append(equity)
            adverse_curve.append(equity)
        trades.append(Trade(index, side, leverage, entry_index, pd.Timestamp(frame.open_time.iloc[entry_index]).isoformat(),
                            float(price), end, pd.Timestamp(frame.open_time.iloc[end]).isoformat(), exit_reason,
                            float(gross), float(fees), float(funding), float(equity-before), float(before), float(equity), end-entry_index, None))
        curve.append(equity)
        adverse_curve.append(equity)
        available = end + 1
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]
    result = BacktestResult(float(initial_equity), float(equity), float(equity-initial_equity), float(equity/initial_equity-1),
                            _max_drawdown(curve), len(trades), sum(t.direction == 1 for t in trades),
                            sum(t.direction == -1 for t in trades), len(wins)/len(trades) if trades else 0.,
                            sum(wins)/abs(sum(losses)) if losses else None, sum(t.gross_pnl for t in trades),
                            sum(t.fees for t in trades), sum(t.funding for t in trades), 0, rejected)
    diagnostics = {"engine": "ohlc-stress-v1", "stress": asdict(stress),
                   "adverse_price_sampled_drawdown": _max_drawdown(adverse_curve),
                   "warning": "OHLC penetration is NOT a queue model; market slippage/fees are scenarios. Adverse-price DD uses possible pre-TP extrema and prior closes, not true intrabar or exchange mark DD. No liquidation model; exposure <=1x only."}
    return result, trades, diagnostics
