from __future__ import annotations

import argparse
import gc
import json
import time
from dataclasses import asdict
from pathlib import Path

import torch  # Import before pandas on Windows to avoid a DLL load-order conflict.
import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import (
    CostModel,
    ExecutionConfig,
    result_dict,
    run_backtest,
    trade_dict,
)
from agentic_alpha_lab.models.kronos_adapter import KronosAdapter
from agentic_alpha_lab.signals.forecast_signal import forecast_to_signal, signal_dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rolling Kronos forecast and BTC futures backtest")
    parser.add_argument("--variant", choices=["mini", "small", "base"], default="mini")
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--kronos-repo", type=Path, default=Path("../Kronos"))
    parser.add_argument("--model-root", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--lookback", type=int, default=512)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--max-windows", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--threshold-bps", type=float, default=12.0)
    parser.add_argument("--atr-window", type=int, default=14)
    parser.add_argument("--entry-limit-offset-bps", type=float, default=0.0)
    parser.add_argument("--entry-expiry-bars", type=int, default=1)
    parser.add_argument("--stop-atr", type=float, default=1.25)
    parser.add_argument("--tp1-atr", type=float, default=1.0)
    parser.add_argument("--tp2-atr", type=float, default=2.0)
    parser.add_argument("--tp1-fraction", type=float, default=0.5)
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--fee-rate", type=float, default=0.0002)
    parser.add_argument("--funding-long-rate", type=float, default=0.0001)
    parser.add_argument("--funding-short-rate", type=float, default=0.0)
    parser.add_argument("--funding-hours", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candles = pd.read_parquet(args.data).sort_values("open_time").reset_index(drop=True)
    candles["open_time"] = pd.to_datetime(candles["open_time"], utc=True)
    candles["close_time"] = pd.to_datetime(candles["close_time"], utc=True)
    first_index = args.lookback - 1
    last_index_exclusive = len(candles) - args.horizon
    indices = list(range(first_index, last_index_exclusive, args.stride))
    if args.max_windows > 0:
        indices = indices[-args.max_windows :]
    if not indices:
        raise ValueError("No rolling windows are available")

    print(
        f"Loading Kronos-{args.variant}; windows={len(indices)}, "
        f"lookback={args.lookback}, horizon={args.horizon}, stride={args.stride}"
    )
    adapter = KronosAdapter(args.variant, args.kronos_repo, args.device, args.model_root)
    started = time.perf_counter()
    signal_rows: list[dict[str, object]] = []

    for batch_start in range(0, len(indices), args.batch_size):
        batch_indices = indices[batch_start : batch_start + args.batch_size]
        contexts = [
            candles.iloc[index - args.lookback + 1 : index + 1].copy()
            for index in batch_indices
        ]
        future_times = [
            candles["open_time"].iloc[index + 1 : index + 1 + args.horizon].reset_index(drop=True)
            for index in batch_indices
        ]
        predictions = adapter.forecast_batch(
            contexts,
            future_times,
            temperature=args.temperature,
            top_k=args.top_k,
            top_p=args.top_p,
            sample_count=args.sample_count,
        )
        for index, prediction in zip(batch_indices, predictions):
            signal = forecast_to_signal(
                candles=candles,
                bar_index=index,
                prediction=prediction,
                threshold_bps=args.threshold_bps,
                atr_window=args.atr_window,
                entry_limit_offset_bps=args.entry_limit_offset_bps,
                stop_atr=args.stop_atr,
                tp1_atr=args.tp1_atr,
                tp2_atr=args.tp2_atr,
            )
            row = signal_dict(signal)
            actual_return = float(candles["close"].iloc[index + args.horizon] / candles["close"].iloc[index] - 1.0)
            row["actual_return"] = actual_return
            row["direction_correct"] = bool(signal.direction * actual_return > 0) if signal.direction else None
            signal_rows.append(row)
        completed = min(batch_start + len(batch_indices), len(indices))
        print(f"Forecasted {completed}/{len(indices)} windows")

    inference_seconds = time.perf_counter() - started
    signals = pd.DataFrame(signal_rows)
    costs = CostModel(
        fee_rate_per_fill=args.fee_rate,
        funding_long_rate=args.funding_long_rate,
        funding_short_rate=args.funding_short_rate,
        funding_interval_hours=args.funding_hours,
    )
    execution = ExecutionConfig(
        entry_expiry_bars=args.entry_expiry_bars,
        max_holding_bars=args.horizon,
        tp1_fraction=args.tp1_fraction,
        leverage=args.leverage,
        intrabar_policy="stop_first",
    )
    result, trades = run_backtest(
        candles=candles,
        signals=signals,
        initial_equity=args.initial_equity,
        costs=costs,
        execution=execution,
    )

    actionable = signals.loc[signals["direction"] != 0]
    directional_accuracy = (
        float(actionable["direction_correct"].mean()) if len(actionable) else None
    )
    metadata = {
        "variant": args.variant,
        "data": str(args.data.resolve()),
        "first_signal_time": signals["signal_time"].iloc[0],
        "last_signal_time": signals["signal_time"].iloc[-1],
        "windows": len(signals),
        "actionable_signals": len(actionable),
        "coverage": float(len(actionable) / len(signals)),
        "directional_accuracy_at_coverage": directional_accuracy,
        "inference_seconds": inference_seconds,
        "seconds_per_window": inference_seconds / len(signals),
        "model": {
            "lookback": args.lookback,
            "horizon": args.horizon,
            "temperature": args.temperature,
            "top_k": args.top_k,
            "top_p": args.top_p,
            "sample_count": args.sample_count,
        },
        "signal": {
            "threshold_bps": args.threshold_bps,
            "atr_window": args.atr_window,
            "entry_limit_offset_bps": args.entry_limit_offset_bps,
            "stop_atr": args.stop_atr,
            "tp1_atr": args.tp1_atr,
            "tp2_atr": args.tp2_atr,
        },
        "costs": asdict(costs),
        "execution": asdict(execution),
        "backtest": result_dict(result),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"kronos_{args.variant}_{len(signals)}w_h{args.horizon}_s{args.stride}"
    signals.to_csv(args.output_dir / f"{stem}_signals.csv", index=False)
    pd.DataFrame([trade_dict(trade) for trade in trades]).to_csv(
        args.output_dir / f"{stem}_trades.csv", index=False
    )
    (args.output_dir / f"{stem}_summary.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))

    del adapter
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
