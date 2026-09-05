from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import torch  # Import before pandas on Windows to avoid a DLL load-order conflict.
import pandas as pd

from agentic_alpha_lab.models.kronos_adapter import KronosAdapter, summary_dict
from agentic_alpha_lab.signals.forecast_signal import forecast_to_signal, signal_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast from the latest closed BTC candle")
    parser.add_argument("--variants", nargs="+", default=["mini", "small", "base"])
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--kronos-repo", type=Path, default=Path("../Kronos"))
    parser.add_argument("--model-root", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--lookback", type=int, default=512)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--threshold-bps", type=float, default=12.0)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candles = pd.read_parquet(args.data).sort_values("open_time").reset_index(drop=True)
    context = candles.tail(args.lookback).copy()
    interval = pd.Timedelta(minutes=5)
    first_future = pd.Timestamp(context["open_time"].iloc[-1]) + interval
    future_timestamps = pd.date_range(first_future, periods=args.horizon, freq=interval)
    results: list[dict[str, object]] = []

    for variant in args.variants:
        adapter = KronosAdapter(
            variant=variant,
            repo_path=args.kronos_repo,
            device=args.device,
            model_root=args.model_root,
        )
        prediction, summary = adapter.forecast(
            context,
            future_timestamps,
            temperature=0.6,
            top_k=1,
            top_p=1.0,
            sample_count=1,
        )
        signal = forecast_to_signal(
            candles=candles,
            bar_index=len(candles) - 1,
            prediction=prediction,
            threshold_bps=args.threshold_bps,
        )
        results.append({"forecast": summary_dict(summary), "signal": signal_dict(signal)})
        del adapter
        gc.collect()
        torch.cuda.empty_cache()

    directions = [int(item["signal"]["direction"]) for item in results]
    vote = sum(directions)
    ensemble = "LONG" if vote > 0 else "SHORT" if vote < 0 else "WAIT"
    payload = {
        "research_only": True,
        "ensemble_vote": ensemble,
        "note": "Uncalibrated zero-shot forecast; do not execute as a live order.",
        "models": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

