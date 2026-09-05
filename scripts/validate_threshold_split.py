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


def evaluate(candles: pd.DataFrame, signals: pd.DataFrame, threshold_bps: float, holding_bars: int) -> dict[str, object]:
    selected = signals.copy()
    selected.loc[selected["predicted_return"].abs() <= threshold_bps / 10_000.0, "direction"] = 0
    result, _ = run_backtest(
        candles,
        selected,
        initial_equity=10_000.0,
        costs=CostModel(
            fee_rate_per_fill=0.0002,
            funding_long_rate=0.0001,
            funding_short_rate=0.0,
            funding_interval_hours=8,
        ),
        execution=ExecutionConfig(
            entry_expiry_bars=1,
            max_holding_bars=holding_bars,
            tp1_fraction=0.5,
            leverage=1.0,
        ),
    )
    actionable = selected.loc[selected["direction"] != 0]
    row = {
        "threshold_bps": threshold_bps,
        "signals": len(selected),
        "actionable_signals": len(actionable),
        "coverage": len(actionable) / len(selected) if len(selected) else 0.0,
        "directional_accuracy": float(actionable["direction_correct"].mean()) if len(actionable) else None,
    }
    row.update(result_dict(result))
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose a threshold on validation and audit it on an embargoed test split")
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--thresholds-bps", nargs="+", type=float, default=[20, 30, 40, 60, 80, 100])
    parser.add_argument("--holding-bars", type=int, default=48)
    parser.add_argument("--bar-minutes", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candles = pd.read_parquet(args.data)
    signals = align_signal_indices(candles, pd.read_csv(args.signals))
    signals["signal_time"] = pd.to_datetime(signals["signal_time"], utc=True)
    signals = signals.sort_values("signal_time").reset_index(drop=True)
    split_time = signals["signal_time"].iloc[len(signals) // 2]
    embargo = pd.Timedelta(minutes=args.holding_bars * args.bar_minutes)
    validation = signals.loc[signals["signal_time"] < split_time].copy()
    test = signals.loc[signals["signal_time"] >= split_time + embargo].copy()
    if validation.empty or test.empty:
        raise ValueError("Validation/test split is empty")

    validation_rows = [evaluate(candles, validation, threshold, args.holding_bars) for threshold in args.thresholds_bps]
    best = max(validation_rows, key=lambda row: (float(row["total_return"]), -float(row["threshold_bps"])))
    chosen = float(best["threshold_bps"])
    test_row = evaluate(candles, test, chosen, args.holding_bars)
    payload = {
        "split_time": split_time.isoformat(),
        "embargo": str(embargo),
        "validation_first": validation["signal_time"].min().isoformat(),
        "validation_last": validation["signal_time"].max().isoformat(),
        "test_first": test["signal_time"].min().isoformat(),
        "test_last": test["signal_time"].max().isoformat(),
        "selection_metric": "validation_total_return",
        "chosen_threshold_bps": chosen,
        "validation_sweep": validation_rows,
        "locked_test": test_row,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
