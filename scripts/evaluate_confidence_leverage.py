from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.backtest.engine import (
    CostModel,
    ExecutionConfig,
    align_signal_indices,
    result_dict,
    run_backtest,
)


def result_with_index(result) -> dict[str, object]:
    payload = result_dict(result)
    payload["capital_index"] = 100.0 * result.final_equity / result.initial_equity
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare 1x and forecast-strength leverage")
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--holding-bars", type=int, required=True)
    parser.add_argument("--threshold-bps", type=float, required=True)
    parser.add_argument("--max-leverage", type=float, default=2.0)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candles = pd.read_parquet(args.data)
    signals = align_signal_indices(candles, pd.read_csv(args.signals))
    threshold = args.threshold_bps / 10_000.0
    signals.loc[signals["predicted_return"].abs() <= threshold, "direction"] = 0
    strength = signals["predicted_return"].abs() / threshold
    signals["leverage"] = 1.0
    signals.loc[strength >= 2.0, "leverage"] = min(1.5, args.max_leverage)
    signals.loc[strength >= 4.0, "leverage"] = args.max_leverage

    costs = CostModel(
        fee_rate_per_fill=0.0002,
        funding_long_rate=0.0001,
        funding_short_rate=0.0,
        funding_interval_hours=8,
    )
    common = dict(
        entry_expiry_bars=1,
        max_holding_bars=args.holding_bars,
        tp1_fraction=0.5,
        maintenance_margin_rate=0.005,
        liquidation_taker_fee_rate=0.00055,
    )
    baseline, _ = run_backtest(
        candles,
        signals.drop(columns=["leverage"]),
        costs=costs,
        execution=ExecutionConfig(leverage=1.0, max_leverage=1.0, **common),
    )
    dynamic, trades = run_backtest(
        candles,
        signals,
        costs=costs,
        execution=ExecutionConfig(leverage=1.0, max_leverage=args.max_leverage, **common),
    )
    payload = {
        "research_only": True,
        "status": "exploratory_not_locked_test",
        "warning": "Forecast magnitude is not calibrated probability; leverage tiers must be refit on validation only.",
        "policy": {
            "base": "1.0x",
            "strength_gte_2": f"{min(1.5, args.max_leverage):.1f}x",
            "strength_gte_4": f"{args.max_leverage:.1f}x",
            "strength_definition": "abs(predicted_return) / signal_threshold",
        },
        "baseline_1x": result_with_index(baseline),
        "dynamic_leverage": result_with_index(dynamic),
        "leverage_distribution": {
            str(level): int(count)
            for level, count in signals.loc[signals["direction"] != 0, "leverage"].value_counts().sort_index().items()
        },
        "trade_leverage_distribution": {
            str(level): sum(trade.leverage == level for trade in trades)
            for level in sorted({trade.leverage for trade in trades})
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
