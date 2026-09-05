from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    fee_rate_per_fill: float = 0.0002
    funding_long_rate: float = 0.0001
    funding_short_rate: float = 0.0
    funding_interval_hours: int = 8


@dataclass(frozen=True)
class ExecutionConfig:
    entry_expiry_bars: int = 1
    max_holding_bars: int = 12
    tp1_fraction: float = 0.5
    leverage: float = 1.0
    max_leverage: float = 1.0
    maintenance_margin_rate: float = 0.005
    liquidation_taker_fee_rate: float = 0.00055
    intrabar_policy: str = "stop_first"


@dataclass
class Trade:
    signal_index: int
    direction: int
    leverage: float
    entry_index: int
    entry_time: str
    entry_price: float
    exit_index: int
    exit_time: str
    exit_reason: str
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    equity_before: float
    equity_after: float
    holding_bars: int
    liquidation_price: float | None


@dataclass(frozen=True)
class BacktestResult:
    initial_equity: float
    final_equity: float
    net_profit: float
    total_return: float
    max_drawdown: float
    trades: int
    long_trades: int
    short_trades: int
    win_rate: float
    profit_factor: float | None
    gross_pnl: float
    fees: float
    funding: float
    liquidations: int
    rejected_or_unfilled_signals: int


def _entry_fill(bar: pd.Series, direction: int, limit: float) -> float | None:
    if direction == 1:
        if float(bar["low"]) > limit:
            return None
        return min(float(bar["open"]), limit) if float(bar["open"]) <= limit else limit
    if float(bar["high"]) < limit:
        return None
    return max(float(bar["open"]), limit) if float(bar["open"]) >= limit else limit


def _stop_fill(bar: pd.Series, direction: int, stop: float) -> float | None:
    if direction == 1:
        if float(bar["low"]) > stop:
            return None
        return min(float(bar["open"]), stop)
    if float(bar["high"]) < stop:
        return None
    return max(float(bar["open"]), stop)


def _take_profit_fill(bar: pd.Series, direction: int, target: float) -> float | None:
    if direction == 1:
        if float(bar["high"]) < target:
            return None
        return max(float(bar["open"]), target)
    if float(bar["low"]) > target:
        return None
    return min(float(bar["open"]), target)


def _liquidation_price(
    entry_price: float,
    direction: int,
    leverage: float,
    maintenance_margin_rate: float,
) -> float | None:
    if leverage <= 1.0:
        return None
    if direction == 1:
        return entry_price * (1.0 - 1.0 / leverage) / (1.0 - maintenance_margin_rate)
    return entry_price * (1.0 + 1.0 / leverage) / (1.0 + maintenance_margin_rate)


def _liquidation_fill(bar: pd.Series, direction: int, price: float | None) -> float | None:
    if price is None:
        return None
    if direction == 1:
        if float(bar["low"]) > price:
            return None
        return min(float(bar["open"]), price)
    if float(bar["high"]) < price:
        return None
    return max(float(bar["open"]), price)


def _is_funding_time(timestamp: pd.Timestamp, interval_hours: int) -> bool:
    utc = timestamp.tz_convert("UTC") if timestamp.tzinfo else timestamp.tz_localize("UTC")
    return utc.minute == 0 and utc.second == 0 and utc.hour % interval_hours == 0


def _max_drawdown(equity: list[float]) -> float:
    values = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    return float(drawdowns.min())


def align_signal_indices(candles: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    """Realign persisted signals after a rolling dataset drops older candles."""
    if "signal_time" not in signals or "close_time" not in candles:
        raise ValueError("signal_time and close_time are required for alignment")
    close_times = pd.to_datetime(candles["close_time"], utc=True)
    lookup = pd.Series(candles.index, index=close_times)
    aligned = signals.copy()
    signal_times = pd.to_datetime(aligned["signal_time"], utc=True)
    indices = signal_times.map(lookup)
    if indices.isna().any():
        missing = signal_times.loc[indices.isna()].iloc[0]
        raise ValueError(f"Signal time is absent from candle data: {missing.isoformat()}")
    aligned["bar_index"] = indices.astype(int).to_numpy()
    return aligned


def run_backtest(
    candles: pd.DataFrame,
    signals: pd.DataFrame,
    initial_equity: float = 10_000.0,
    costs: CostModel | None = None,
    execution: ExecutionConfig | None = None,
) -> tuple[BacktestResult, list[Trade]]:
    """Run a conservative, non-overlapping bracket backtest."""
    costs = costs or CostModel()
    execution = execution or ExecutionConfig()
    if execution.intrabar_policy != "stop_first":
        raise ValueError("Only conservative stop_first intrabar policy is supported")
    if not 0.0 < execution.tp1_fraction < 1.0:
        raise ValueError("tp1_fraction must be between zero and one")
    if execution.leverage <= 0 or execution.max_leverage < execution.leverage:
        raise ValueError("Leverage must be positive and not exceed max_leverage")

    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = signals.sort_values("bar_index").reset_index(drop=True)
    equity = float(initial_equity)
    equity_points = [equity]
    trades: list[Trade] = []
    next_available_index = 0
    rejected = 0

    for signal in signals.itertuples(index=False):
        signal_index = int(signal.bar_index)
        direction = int(signal.direction)
        if direction == 0 or signal_index < next_available_index:
            rejected += 1
            continue

        entry_index = None
        entry_price = None
        first_entry_bar = signal_index + 1
        last_entry_bar = min(signal_index + execution.entry_expiry_bars, len(candles) - 1)
        for index in range(first_entry_bar, last_entry_bar + 1):
            candidate = _entry_fill(candles.iloc[index], direction, float(signal.entry_limit))
            if candidate is not None:
                entry_index = index
                entry_price = candidate
                break
        if entry_index is None or entry_price is None:
            rejected += 1
            continue

        equity_before = equity
        requested_leverage = float(getattr(signal, "leverage", execution.leverage))
        leverage = min(max(requested_leverage, execution.leverage), execution.max_leverage)
        notional = equity_before * leverage
        entry_fee = notional * costs.fee_rate_per_fill
        equity -= entry_fee
        fees = entry_fee
        funding = 0.0
        gross_pnl = 0.0
        remaining = 1.0
        tp1_done = False
        exit_reason = "time"
        exit_index = min(entry_index + execution.max_holding_bars, len(candles) - 1)
        final_exit_price = float(candles.iloc[exit_index]["open"])
        liquidation_price = _liquidation_price(
            entry_price,
            direction,
            leverage,
            execution.maintenance_margin_rate,
        )

        for index in range(entry_index, exit_index):
            bar = candles.iloc[index]
            bar_time = pd.Timestamp(bar["open_time"])
            if index > entry_index and _is_funding_time(bar_time, costs.funding_interval_hours):
                rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
                charge = notional * remaining * rate
                funding += charge
                equity -= charge

            liquidation_fill = _liquidation_fill(bar, direction, liquidation_price)
            stop_fill = _stop_fill(bar, direction, float(signal.stop_loss))
            if liquidation_fill is not None and stop_fill is not None:
                opened_beyond_liquidation = (
                    direction == 1 and float(bar["open"]) <= float(liquidation_price)
                ) or (
                    direction == -1 and float(bar["open"]) >= float(liquidation_price)
                )
                if not opened_beyond_liquidation:
                    liquidation_fill = None
            if liquidation_fill is not None:
                fraction = remaining
                pnl = direction * (liquidation_fill - entry_price) / entry_price * notional * fraction
                exit_fee = (
                    notional
                    * fraction
                    * (liquidation_fill / entry_price)
                    * execution.liquidation_taker_fee_rate
                )
                gross_pnl += pnl
                fees += exit_fee
                equity = max(0.0, equity + pnl - exit_fee)
                remaining = 0.0
                exit_reason = "liquidation"
                exit_index = index
                final_exit_price = liquidation_fill
                equity_points.append(equity)
                break

            if stop_fill is not None:
                fraction = remaining
                pnl = direction * (stop_fill - entry_price) / entry_price * notional * fraction
                exit_fee = notional * fraction * (stop_fill / entry_price) * costs.fee_rate_per_fill
                gross_pnl += pnl
                fees += exit_fee
                equity += pnl - exit_fee
                remaining = 0.0
                exit_reason = "stop"
                exit_index = index
                final_exit_price = stop_fill
                equity_points.append(equity)
                break

            if not tp1_done:
                tp1_fill = _take_profit_fill(bar, direction, float(signal.take_profit_1))
                if tp1_fill is not None:
                    fraction = execution.tp1_fraction
                    pnl = direction * (tp1_fill - entry_price) / entry_price * notional * fraction
                    exit_fee = notional * fraction * (tp1_fill / entry_price) * costs.fee_rate_per_fill
                    gross_pnl += pnl
                    fees += exit_fee
                    equity += pnl - exit_fee
                    remaining -= fraction
                    tp1_done = True

            tp2_fill = _take_profit_fill(bar, direction, float(signal.take_profit_2))
            if remaining > 0 and tp2_fill is not None:
                fraction = remaining
                pnl = direction * (tp2_fill - entry_price) / entry_price * notional * fraction
                exit_fee = notional * fraction * (tp2_fill / entry_price) * costs.fee_rate_per_fill
                gross_pnl += pnl
                fees += exit_fee
                equity += pnl - exit_fee
                remaining = 0.0
                exit_reason = "tp2"
                exit_index = index
                final_exit_price = tp2_fill
                equity_points.append(equity)
                break

            mark_price = float(bar["close"])
            mark_pnl = direction * (mark_price - entry_price) / entry_price * notional * remaining
            equity_points.append(max(0.0, equity + mark_pnl))

        if remaining > 0:
            bar = candles.iloc[exit_index]
            bar_time = pd.Timestamp(bar["open_time"])
            if _is_funding_time(bar_time, costs.funding_interval_hours):
                rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
                charge = notional * remaining * rate
                funding += charge
                equity -= charge
            final_exit_price = float(bar["open"])
            pnl = direction * (final_exit_price - entry_price) / entry_price * notional * remaining
            exit_fee = notional * remaining * (final_exit_price / entry_price) * costs.fee_rate_per_fill
            gross_pnl += pnl
            fees += exit_fee
            equity += pnl - exit_fee
            exit_reason = "time_after_tp1" if tp1_done else "time"
            remaining = 0.0
            equity_points.append(equity)

        trade = Trade(
            signal_index=signal_index,
            direction=direction,
            leverage=leverage,
            entry_index=entry_index,
            entry_time=pd.Timestamp(candles["open_time"].iloc[entry_index]).isoformat(),
            entry_price=float(entry_price),
            exit_index=exit_index,
            exit_time=pd.Timestamp(candles["open_time"].iloc[exit_index]).isoformat(),
            exit_reason=exit_reason,
            gross_pnl=float(gross_pnl),
            fees=float(fees),
            funding=float(funding),
            net_pnl=float(equity - equity_before),
            equity_before=float(equity_before),
            equity_after=float(equity),
            holding_bars=int(exit_index - entry_index),
            liquidation_price=float(liquidation_price) if liquidation_price is not None else None,
        )
        trades.append(trade)
        equity_points.append(equity)
        next_available_index = exit_index + 1

    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    result = BacktestResult(
        initial_equity=float(initial_equity),
        final_equity=float(equity),
        net_profit=float(equity - initial_equity),
        total_return=float(equity / initial_equity - 1.0),
        max_drawdown=_max_drawdown(equity_points),
        trades=len(trades),
        long_trades=sum(trade.direction == 1 for trade in trades),
        short_trades=sum(trade.direction == -1 for trade in trades),
        win_rate=float(len(wins) / len(trades)) if trades else 0.0,
        profit_factor=float(profit_factor) if profit_factor is not None else None,
        gross_pnl=float(sum(trade.gross_pnl for trade in trades)),
        fees=float(sum(trade.fees for trade in trades)),
        funding=float(sum(trade.funding for trade in trades)),
        liquidations=sum(trade.exit_reason == "liquidation" for trade in trades),
        rejected_or_unfilled_signals=rejected,
    )
    return result, trades


def result_dict(result: BacktestResult) -> dict[str, object]:
    return asdict(result)


def trade_dict(trade: Trade) -> dict[str, object]:
    return asdict(trade)
