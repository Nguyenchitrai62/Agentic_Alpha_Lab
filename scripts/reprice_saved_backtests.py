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
    trade_dict,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprice saved signals without rerunning inference")
    parser.add_argument("--reports-dir", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"),
    )
    parser.add_argument("--fee-rate", type=float, default=0.0002)
    args = parser.parse_args()

    candles = pd.read_parquet(args.data)
    summary_paths = [
        path
        for reports_dir in args.reports_dir
        for path in sorted(reports_dir.glob("kronos_*_summary.json"))
    ]
    for summary_path in summary_paths:
        reports_dir = summary_path.parent
        stem = summary_path.name.removesuffix("_summary.json")
        signals_path = reports_dir / f"{stem}_signals.csv"
        trades_path = reports_dir / f"{stem}_trades.csv"
        if not signals_path.exists():
            continue

        metadata = json.loads(summary_path.read_text(encoding="utf-8"))
        signals = align_signal_indices(candles, pd.read_csv(signals_path))
        previous_costs = metadata["costs"]
        costs = CostModel(
            fee_rate_per_fill=args.fee_rate,
            funding_long_rate=float(previous_costs["funding_long_rate"]),
            funding_short_rate=float(previous_costs["funding_short_rate"]),
            funding_interval_hours=int(previous_costs["funding_interval_hours"]),
        )
        execution = ExecutionConfig(**metadata["execution"])
        result, trades = run_backtest(
            candles,
            signals,
            initial_equity=float(metadata["backtest"]["initial_equity"]),
            costs=costs,
            execution=execution,
        )
        metadata["costs"] = {
            "fee_rate_per_fill": costs.fee_rate_per_fill,
            "funding_long_rate": costs.funding_long_rate,
            "funding_short_rate": costs.funding_short_rate,
            "funding_interval_hours": costs.funding_interval_hours,
        }
        metadata["backtest"] = result_dict(result)
        summary_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        pd.DataFrame([trade_dict(trade) for trade in trades]).to_csv(trades_path, index=False)
        print(f"{stem}: return={result.total_return:.4%}, fees={result.fees:.2f}")


if __name__ == "__main__":
    main()
