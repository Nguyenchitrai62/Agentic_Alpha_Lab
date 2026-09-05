"""Causal frequency-limited swing policy and reference-engine portfolio report."""
from collections import Counter
from dataclasses import asdict
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.swing import choose
from agentic_alpha_lab.backtest.engine import run_backtest, CostModel, ExecutionConfig


def swing_signals(predictions, decisions, config):
    signals, monthly = [], Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    for p, row in zip(predictions, decisions.itertuples()):
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= config["policy"]["maximum_signals_per_month"]:
            continue
        signal = choose(p, row.close, row.atr5, row.atr4, config)
        if signal["action"] == "WAIT":
            continue
        signals.append({"bar_index": row.bar_index, "signal_time": timestamp, **signal})
        monthly[month] += 1
        next_allowed = timestamp + pd.Timedelta(days=config["policy"]["cooldown_days"])
    return pd.DataFrame(signals) if signals else pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def evaluate(predictions, decisions, candles, config, split):
    signals = swing_signals(predictions, decisions, config)
    execution = ExecutionConfig(entry_expiry_bars=config["entry_expiry_bars"], max_holding_bars=max(config["holding_days"]) * 288)
    result, trades = run_backtest(candles, signals, 100, CostModel(**config["costs"]), execution)
    stress, _ = run_backtest(candles, signals, 100, CostModel(**dict(config["costs"], fee_rate_per_fill=0.00055)), execution)
    months = pd.period_range(pd.Timestamp(decisions.signal_time.iloc[0]).tz_localize(None),
                            pd.Timestamp(decisions.signal_time.iloc[-1]).tz_localize(None), freq="M")
    counts = {str(m): 0 for m in months}
    if len(signals):
        counts.update(signals.signal_time.dt.strftime("%Y-%m").value_counts().astype(int).to_dict())
    report = {"split": split, "result": asdict(result), "fee_stress": asdict(stress), "signals_by_month": counts,
              "signal_count": len(signals), "decision_count": len(decisions), "coverage": len(signals) / len(decisions),
              "baseline_wait_equity": 100, "test_used_for_tuning": False,
              "caveats": ["OHLC fill proxy; no queue or mark price", "SL/timeout market-like at scenario fee",
                          "1x only; close-sampled DD", "frequency cap counts alerts, not necessarily fills",
                          "scores uncalibrated; no mandatory minimum 1 alert", "historical exploratory evaluation"]}
    return report, signals, pd.DataFrame([asdict(t) for t in trades])
