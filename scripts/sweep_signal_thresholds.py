from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.backtest.engine import (
    CostModel,
    ExecutionConfig,
    align_signal_indices,
    result_dict,
    run_backtest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only threshold sweep over saved forecasts")
    parser.add_argument("--signals-dir", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--thresholds-bps", nargs="+", type=float, default=[12, 16, 20, 30, 40, 60])
    parser.add_argument("--base-threshold-bps", type=float, default=12.0)
    parser.add_argument("--holding-bars", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if min(args.thresholds_bps) < args.base_threshold_bps:
        raise ValueError("Saved WAIT rows do not contain brackets; thresholds must not be below the original threshold")

    candles = pd.read_parquet(args.data)
    rows: list[dict[str, object]] = []
    for path in sorted(args.signals_dir.glob("kronos_*_signals.csv")):
        variant = path.name.split("_")[1]
        original = align_signal_indices(candles, pd.read_csv(path))
        for threshold_bps in args.thresholds_bps:
            signals = original.copy()
            active = signals["predicted_return"].abs() > threshold_bps / 10_000.0
            signals.loc[~active, "direction"] = 0
            result, _ = run_backtest(
                candles,
                signals,
                initial_equity=10_000.0,
                costs=CostModel(
                    fee_rate_per_fill=0.0002,
                    funding_long_rate=0.0001,
                    funding_short_rate=0.0,
                    funding_interval_hours=8,
                ),
                execution=ExecutionConfig(
                    entry_expiry_bars=1,
                    max_holding_bars=args.holding_bars,
                    tp1_fraction=0.5,
                    leverage=1.0,
                ),
            )
            actionable = signals.loc[signals["direction"] != 0]
            row = {
                "variant": variant,
                "threshold_bps": threshold_bps,
                "actionable_signals": len(actionable),
                "coverage": len(actionable) / len(signals),
                "directional_accuracy": float(actionable["direction_correct"].mean()) if len(actionable) else None,
            }
            row.update(result_dict(result))
            rows.append(row)

    output = pd.DataFrame(rows).sort_values(["variant", "threshold_bps"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(output.to_string(index=False))
    print(f"Saved threshold sweep to {args.output.resolve()}")


if __name__ == "__main__":
    main()
