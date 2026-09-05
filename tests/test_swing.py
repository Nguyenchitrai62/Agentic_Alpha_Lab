import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import torch
from agentic_alpha_lab.data.swing import prices, grid, fast_outcome, funding_flags, context_features, choose
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.swing import swing_signals
from agentic_alpha_lab.models.swing import swing_loss


def config():
    return json.loads((Path(__file__).resolve().parents[1] / "configs/kronos_swing.json").read_text())


def path(seed, n=2100):
    rng = np.random.default_rng(seed)
    op = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    close = op * np.exp(rng.normal(0, 0.002, n))
    t = pd.date_range("2024-01-01T07:00Z", periods=n, freq="5min")
    return pd.DataFrame({"open_time": t, "open": op, "close": close,
                         "high": np.maximum(op, close) * 1.001, "low": np.minimum(op, close) * .999})


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_fast_swing_labels_match_reference_for_all_brackets(seed):
    c, cfg = path(seed), config()
    ohlc = c[["open", "high", "low", "close"]].to_numpy()
    for candidate in grid(cfg):
        signal = prices(float(c.close.iloc[1]), .2, 1, candidate, cfg)
        actual = fast_outcome(ohlc, funding_flags(c), 1, signal, cfg)
        reference, trades = run_backtest(c, pd.DataFrame([{"bar_index": 1, **signal}]), 100,
                            CostModel(**cfg["costs"]), ExecutionConfig(entry_expiry_bars=12, max_holding_bars=2016))
        np.testing.assert_allclose(actual, [reference.net_profit, bool(trades), reference.net_profit > 0], atol=1e-5)


def test_swing_wait_does_not_require_55_percent_win_and_frequency_is_causal():
    cfg = config()
    p = np.zeros((len(grid(cfg)), 6), np.float32)
    p[0, 0] = 1
    p[0, 5] = -1  # asymmetric payoff may have positive expectancy despite low win rate
    assert choose(p, 100, .1, 1, cfg)["action"] == "LONG"
    t = pd.date_range("2025-01-01", periods=90, freq="D", tz="UTC")
    d = pd.DataFrame({"signal_time": t, "bar_index": np.arange(90), "close": 100, "atr5": .1, "atr4": 1})
    predictions = np.repeat(p[None], 90, 0)
    signals = swing_signals(predictions, d, cfg)
    assert signals.signal_time.dt.month.value_counts().max() <= 4
    earlier = swing_signals(predictions[:20], d.iloc[:20], cfg)
    pd.testing.assert_frame_equal(earlier, signals.loc[signals.signal_time < t[20]].reset_index(drop=True))


def test_unfilled_outcomes_are_masked_for_conditional_heads():
    p = torch.zeros(2, 16, 6, requires_grad=True)
    labels = torch.zeros(2, 16, 3)
    loss = swing_loss(p, torch.zeros(2, 2), labels, torch.zeros(2, 2))
    loss.backward()
    assert p.grad[..., :4].abs().sum() == 0
    assert p.grad[..., 5].abs().sum() == 0
    assert p.grad[..., 4].abs().sum() > 0


def test_swing_gap_and_timeouts_and_horizon_validation():
    cfg = config()
    c = path(9)
    c.loc[:, ["open", "high", "low", "close"]] = 100.
    s = {"direction": 1, "entry_limit": 100., "stop_loss": 95., "take_profit_1": 105., "take_profit_2": 110., "holding_bars": 2016}
    actual = fast_outcome(c[["open", "high", "low", "close"]].to_numpy(), funding_flags(c), 1, s, cfg)
    result, _ = run_backtest(c, pd.DataFrame([{"bar_index": 1, **s}]), 100, CostModel(**cfg["costs"]),
                            ExecutionConfig(entry_expiry_bars=12, max_holding_bars=2016))
    assert actual[0] == pytest.approx(result.net_profit, abs=1e-6)
    assert actual[0] < -.24  # fee + approximately 21 funding boundaries
    with pytest.raises(ValueError, match="Incomplete"):
        fast_outcome(c[["open", "high", "low", "close"]].to_numpy(), funding_flags(c), 100, s, cfg)


def test_daily_context_and_atr_remain_past_only():
    from agentic_alpha_lab.data.swing import SwingStore
    cfg = config()
    cfg["context"] = 32
    c = path(11, 11000)
    c["close_time"] = c.open_time + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1)
    c["volume"], c["quote_volume"] = 1., c.close
    as_of = c.close_time.iloc[10000]
    before = SwingStore(c, cfg).sample(as_of)
    c.loc[10001:, ["open", "high", "low", "close", "volume", "quote_volume"]] *= 3
    after = SwingStore(c, cfg).sample(as_of)
    for left, right in zip(before, after):
        np.testing.assert_array_equal(left, right)
    assert before[0].shape == (5, 32, 6)
    assert before[3].shape == (40,)


def test_per_signal_horizon_cap_rejects_invalid_values():
    c = path(12)
    s = {"bar_index": 1, "direction": 1, "entry_limit": 100., "stop_loss": 90.,
         "take_profit_1": 110., "take_profit_2": 120., "holding_bars": 50}
    with pytest.raises(ValueError, match="horizon cap"):
        run_backtest(c, pd.DataFrame([s]), execution=ExecutionConfig(max_holding_bars=10))
