from __future__ import annotations

import pandas as pd
import pytest

from agentic_alpha_lab.backtest.engine import (
    CostModel,
    ExecutionConfig,
    align_signal_indices,
    run_backtest,
)


def candles(start: str = "2026-01-01 00:05:00+00:00", rows: int = 20) -> pd.DataFrame:
    times = pd.date_range(start, periods=rows, freq="5min")
    return pd.DataFrame(
        {
            "open_time": times,
            "close_time": times + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        }
    )


def signal(direction: int = 1, bar_index: int = 0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "bar_index": bar_index,
                "direction": direction,
                "entry_limit": 100.0,
                "stop_loss": 90.0 if direction == 1 else 110.0,
                "take_profit_1": 110.0 if direction == 1 else 90.0,
                "take_profit_2": 120.0 if direction == 1 else 80.0,
            }
        ]
    )


def test_flat_round_trip_charges_two_fills_and_enters_after_signal() -> None:
    result, trades = run_backtest(
        candles(),
        signal(),
        initial_equity=10_000.0,
        costs=CostModel(fee_rate_per_fill=0.0002, funding_long_rate=0.0),
        execution=ExecutionConfig(max_holding_bars=2),
    )
    assert len(trades) == 1
    assert trades[0].entry_index == 1
    assert trades[0].entry_index > trades[0].signal_index
    assert trades[0].fees == pytest.approx(4.0)
    assert result.final_equity == pytest.approx(9_996.0)


def test_long_pays_funding_but_short_does_not() -> None:
    frame = candles(start="2026-01-01 07:45:00+00:00", rows=10)
    execution = ExecutionConfig(max_holding_bars=5)
    costs = CostModel(
        fee_rate_per_fill=0.0,
        funding_long_rate=0.0001,
        funding_short_rate=0.0,
        funding_interval_hours=8,
    )
    long_result, long_trades = run_backtest(frame, signal(1), costs=costs, execution=execution)
    short_result, short_trades = run_backtest(frame, signal(-1), costs=costs, execution=execution)
    assert long_trades[0].funding == pytest.approx(1.0)
    assert long_result.final_equity == pytest.approx(9_999.0)
    assert short_trades[0].funding == 0.0
    assert short_result.final_equity == pytest.approx(10_000.0)


def test_limit_that_is_not_touched_is_not_filled() -> None:
    item = signal()
    item.loc[0, "entry_limit"] = 90.0
    result, trades = run_backtest(candles(), item)
    assert trades == []
    assert result.final_equity == 10_000.0
    assert result.rejected_or_unfilled_signals == 1


def test_stop_wins_when_stop_and_targets_touch_in_same_bar() -> None:
    frame = candles()
    frame.loc[1, ["high", "low"]] = [125.0, 85.0]
    result, trades = run_backtest(
        frame,
        signal(),
        initial_equity=10_000.0,
        costs=CostModel(fee_rate_per_fill=0.0, funding_long_rate=0.0),
        execution=ExecutionConfig(max_holding_bars=2, intrabar_policy="stop_first"),
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop"
    assert trades[0].gross_pnl == pytest.approx(-1_000.0)
    assert result.final_equity == pytest.approx(9_000.0)


def test_saved_signal_is_realigned_by_close_time() -> None:
    frame = candles(rows=4)
    saved = signal(bar_index=99)
    saved["signal_time"] = frame.loc[2, "close_time"].isoformat()
    aligned = align_signal_indices(frame, saved)
    assert aligned.loc[0, "bar_index"] == 2


def test_signal_leverage_scales_compounded_notional() -> None:
    frame = candles(rows=4)
    frame.loc[2:, ["open", "high", "low", "close"]] = 101.0
    leveraged = signal()
    leveraged["leverage"] = 2.0
    result, trades = run_backtest(
        frame,
        leveraged,
        initial_equity=10_000.0,
        costs=CostModel(fee_rate_per_fill=0.0, funding_long_rate=0.0),
        execution=ExecutionConfig(max_holding_bars=1, leverage=1.0, max_leverage=2.0),
    )
    assert trades[0].leverage == 2.0
    assert trades[0].gross_pnl == pytest.approx(200.0)
    assert result.final_equity == pytest.approx(10_200.0)
