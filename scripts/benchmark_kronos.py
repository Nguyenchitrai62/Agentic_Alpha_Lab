from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch  # Import before pandas on Windows to avoid a DLL load-order conflict.
import pandas as pd

from agentic_alpha_lab.models.kronos_adapter import KronosAdapter, summary_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark official Kronos checkpoints")
    parser.add_argument("--variants", nargs="+", default=["mini", "small", "base"])
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--kronos-repo", type=Path, default=Path("../Kronos"))
    parser.add_argument("--model-root", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--lookback", type=int, default=512)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("artifacts/kronos_benchmark.json"))
    args = parser.parse_args()

    frame = pd.read_parquet(args.data).sort_values("open_time").reset_index(drop=True)
    required = args.lookback + args.horizon
    if len(frame) < required:
        raise ValueError(f"Need at least {required} rows, got {len(frame)}")
    context = frame.iloc[-required:-args.horizon].copy()
    future_timestamps = frame["open_time"].iloc[-args.horizon:].reset_index(drop=True)

    results: list[dict[str, object]] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for variant in args.variants:
        print(f"Loading Kronos-{variant}...")
        adapter = KronosAdapter(
            variant=variant,
            repo_path=args.kronos_repo,
            device=args.device,
            model_root=args.model_root,
        )
        prediction, summary = adapter.forecast(
            context=context,
            future_timestamps=future_timestamps,
            temperature=args.temperature,
            top_k=args.top_k,
            top_p=args.top_p,
            sample_count=args.sample_count,
        )
        item = summary_dict(summary)
        item["actual_close_at_horizon"] = float(frame["close"].iloc[-1])
        item["actual_return_at_horizon"] = float(frame["close"].iloc[-1] / context["close"].iloc[-1] - 1.0)
        item["direction_correct"] = bool(
            item["predicted_return"] * item["actual_return_at_horizon"] > 0
        )
        results.append(item)
        print(json.dumps(item, indent=2))
        del adapter
        torch.cuda.empty_cache()

    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved benchmark to {args.output.resolve()}")


if __name__ == "__main__":
    main()
