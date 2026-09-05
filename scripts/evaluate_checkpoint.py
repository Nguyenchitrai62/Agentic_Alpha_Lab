from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import torch
import numpy as np
import pandas as pd
from safetensors.torch import load_file

from agentic_alpha_lab.data.training import verified_split, sha256
from agentic_alpha_lab.models.supervised import MultiHorizonMLP, probabilities, classification_metrics
from agentic_alpha_lab.backtest.engine import ENGINE_VERSION, CostModel, ExecutionConfig, run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Open held-out research split once, with frozen checkpoint policy")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Do not overwrite evaluation evidence")
    metadata = json.loads((args.checkpoint / "metadata.json").read_text(encoding="utf-8"))
    if sha256(args.dataset / "manifest.json") != metadata["dataset_manifest_sha256"]:
        raise ValueError("Checkpoint belongs to a different dataset manifest")
    if sha256(args.checkpoint / "model.safetensors") != metadata["model_sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    if sha256(args.dataset / "candles.parquet") != metadata["dataset_files"]["candles.parquet"]:
        raise ValueError("Candle snapshot hash mismatch")
    frame = verified_split(args.dataset, "test")
    config, features = metadata["config"], metadata["features"]
    x = np.clip((frame[features].to_numpy(float) - metadata["mean"]) / metadata["scale"], -10, 10)
    model = MultiHorizonMLP(len(features), config["model"]["hidden"], len(config["horizons"]))
    model.load_state_dict(load_file(str(args.checkpoint / "model.safetensors")))
    model.eval()
    with torch.no_grad():
        logits, quantiles = model(torch.tensor(x, dtype=torch.float32))
    probs = probabilities(logits.numpy(), metadata["temperature"])
    quantiles = quantiles.numpy() / 100
    policy = config["policy"]
    horizon = policy["horizon"]
    i = config["horizons"].index(horizon)
    classes = probs[:, i].argmax(axis=1)
    direction = classes - 1
    confidence = probs[:, i].max(axis=1)
    median = quantiles[:, i, 1]
    active = (confidence >= policy["minimum_probability"]) & (direction * median >= policy["minimum_return_bps"] / 10000)
    direction = np.where(active, direction, 0)
    entry = frame.close.to_numpy() * (1 - direction * config["entry_offset_bps"] / 10000)
    atr = frame["x_5min_atr"].to_numpy() * frame.close.to_numpy()
    signals = pd.DataFrame({"bar_index": frame.bar_index, "signal_time": frame.signal_time,
                            "direction": direction, "confidence": confidence, "entry_limit": entry,
                            "stop_loss": entry - direction * atr * policy["stop_atr"],
                            "take_profit_1": entry + direction * atr * policy["tp1_atr"],
                            "take_profit_2": entry + direction * atr * policy["tp2_atr"],
                            "leverage": policy["leverage"]})
    candles = pd.read_parquet(args.dataset / "candles.parquet")
    execution = ExecutionConfig(max_holding_bars=horizon, leverage=policy["leverage"], max_leverage=policy["leverage"])
    result, trades = run_backtest(candles, signals, initial_equity=100, costs=CostModel(**config["costs"]), execution=execution)
    # A uniform higher per-fill fee is a simple cost stress, not a queue/slippage simulator.
    stress_costs = {**config["costs"], "fee_rate_per_fill": 0.00055}
    stress, _ = run_backtest(candles, signals, initial_equity=100, costs=CostModel(**stress_costs), execution=execution)
    metrics = {}
    for j, h in enumerate(config["horizons"]):
        truth = frame[f"y_return_{h}"].to_numpy()
        metrics[str(h)] = {**classification_metrics(probs[:, j], frame[f"y_direction_{h}"].to_numpy()),
                           "p10_p90_coverage": float(((truth >= quantiles[:, j, 0]) & (truth <= quantiles[:, j, 2])).mean())}
    report = {"engine_version": ENGINE_VERSION, "status": "opened_exploratory_test_do_not_tune_on_this_interval",
              "dataset_manifest_sha256": metadata["dataset_manifest_sha256"],
              "checkpoint_metadata_sha256": sha256(args.checkpoint / "metadata.json"),
              "test_range": [frame.signal_time.iloc[0].isoformat(), frame.label_end.iloc[-1].isoformat()],
              "policy": policy, "costs": config["costs"], "execution": asdict(execution),
              "assumptions": "OHLC touch fills; stop/timeout market-like at scenario fee; trade-price funding proxy; candle-close DD; no maker queue model",
              "coverage": float(np.mean(direction != 0)), "prediction_rows": len(frame), "prediction_metrics": metrics,
              "backtest": asdict(result), "higher_fee_stress": asdict(stress),
              "candidate_accepted": False, "reason": "Pipeline smoke on already inspected short history; new multi-regime forward evidence required"}
    args.output.mkdir(parents=True)
    signals.to_parquet(args.output / "signals.parquet", index=False)
    pd.DataFrame([asdict(trade) for trade in trades]).to_csv(args.output / "trades.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
