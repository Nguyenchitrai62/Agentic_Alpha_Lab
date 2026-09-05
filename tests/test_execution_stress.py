from dataclasses import asdict
import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress


def frame():
    times = pd.date_range("2026-01-01T07:40:00Z", periods=40, freq="5min")
    return pd.DataFrame({"open_time": times, "close_time": times + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
                         "open": 100., "high": 101., "low": 99., "close": 100.})


def signals(side=1):
    return pd.DataFrame([{"bar_index": 0, "direction": side, "entry_limit": 100., "stop_loss": 90. if side == 1 else 110.,
                          "take_profit_1": 110. if side == 1 else 90., "take_profit_2": 120. if side == 1 else 80.}])


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("side", [1, -1])
def test_zero_stress_matches_frozen_engine(seed, side):
    candles = frame()
    rng = np.random.default_rng(seed)
    op = 100 + np.cumsum(rng.normal(0, 2, len(candles)))
    cl = op + rng.normal(0, 1, len(candles))
    candles["open"], candles["close"] = op, cl
    candles["high"] = np.maximum(op, cl) + rng.uniform(0, 6, len(candles))
    candles["low"] = np.minimum(op, cl) - rng.uniform(0, 6, len(candles))
    sig = pd.concat([signals(side).assign(bar_index=0), signals(-side).assign(bar_index=20)])
    cfg = ExecutionConfig(max_holding_bars=10, entry_expiry_bars=3)
    reference, original = run_backtest(candles, sig, 100, execution=cfg)
    result, trades, diagnostics = run_stress(candles, sig, execution=cfg)
    for field, value in asdict(reference).items():
        assert asdict(result)[field] == pytest.approx(value) if value is not None else asdict(result)[field] is None
    assert [(t.entry_index, t.exit_index, t.exit_reason) for t in trades] == [(t.entry_index, t.exit_index, t.exit_reason) for t in original]
    assert diagnostics["adverse_price_sampled_drawdown"] <= result.max_drawdown + 1e-12


@pytest.mark.parametrize("side", [1, -1])
def test_limit_touch_without_penetration_does_not_fill(side):
    candles = frame()
    candles[["open", "high", "low", "close"]] = 100.
    result, trades, _ = run_stress(candles, signals(side), stress=FillStress(entry_penetration_bps=1))
    assert not trades and result.final_equity == 100


@pytest.mark.parametrize("side", [1, -1])
def test_adverse_market_slippage_costs_both_sides(side):
    cfg = ExecutionConfig(max_holding_bars=2)
    costs = CostModel(fee_rate_per_fill=0, funding_long_rate=0)
    result, _, _ = run_stress(frame(), signals(side), costs=costs, execution=cfg,
                              stress=FillStress(market_exit_slippage_bps=10))
    assert result.final_equity == pytest.approx(99.9)


def test_rejects_unmodeled_leverage():
    with pytest.raises(ValueError, match="<=1x"):
        run_stress(frame(), signals(), execution=ExecutionConfig(leverage=2, max_leverage=2))


def test_partial_exit_reduces_later_funding_in_both_engines():
    candles = frame()
    candles.loc[2, ["open", "high", "low", "close"]] = [110, 111, 109, 110]
    cfg = ExecutionConfig(max_holding_bars=6)
    baseline, old_trades = run_backtest(candles, signals(), 100, execution=cfg)
    result, trades, _ = run_stress(candles, signals(), execution=cfg)
    assert trades[0].funding == pytest.approx(old_trades[0].funding)
    assert trades[0].funding == pytest.approx(.005)
    assert result.final_equity == pytest.approx(baseline.final_equity)


def test_target_touch_can_miss_under_penetration_stress():
    candles = frame()
    candles.loc[2, "high"] = 110
    cfg = ExecutionConfig(max_holding_bars=4)
    original, _, _ = run_stress(candles, signals(), execution=cfg)
    stressed, trades, _ = run_stress(candles, signals(), execution=cfg,
                                     stress=FillStress(target_penetration_bps=5))
    assert original.final_equity > stressed.final_equity
    assert trades[0].exit_reason == "time"


def test_stop_gap_slippage_is_adverse_and_uses_market_fee():
    candles = frame()
    candles.loc[2, ["open", "high", "low", "close"]] = [80, 85, 75, 80]
    result, trades, _ = run_stress(candles, signals(), stress=FillStress(market_exit_slippage_bps=10, market_exit_fee_rate=.00055))
    assert trades[0].exit_reason == "stop"
    assert trades[0].gross_pnl == pytest.approx(-20.08)
    assert trades[0].fees == pytest.approx(.02 + 79.92 * .00055)
    assert result.final_equity == pytest.approx(79.92 - trades[0].fees)
