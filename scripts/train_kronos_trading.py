"""Frozen pretrained Kronos + trainable fusion. No test reads or live orders."""
from __future__ import annotations
import torch  # before pandas on Windows
import argparse
from dataclasses import asdict
import json
import platform
from pathlib import Path
import random
import time
import numpy as np
import pandas as pd
from safetensors.torch import save_file, load_file
from torch.utils.data import DataLoader, TensorDataset
from agentic_alpha_lab.models.kronos_trading import KronosWindowEncoder, BracketFusion, trading_loss
from agentic_alpha_lab.data.kronos_trading import decode_suggestion
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest


def encode(encoder, arrays, batch_size, device, label):
    loader = DataLoader(TensorDataset(torch.from_numpy(arrays["windows"]), torch.from_numpy(arrays["stamps"])),
                        batch_size=batch_size, shuffle=False)
    values = []
    encoder.eval()
    with torch.no_grad():
        for step, (windows, stamps) in enumerate(loader):
            values.append(encoder(windows.to(device), stamps.to(device)).cpu())
            if step % 25 == 0:
                print(f"encode {label} {step+1}/{len(loader)}", flush=True)
    return torch.cat(values)


def validate(model, loader, device):
    model.eval()
    total, count, predictions = 0.0, 0, []
    with torch.no_grad():
        for x, ages, labels in loader:
            prediction = model(x.to(device), ages.to(device))
            loss = trading_loss(prediction, labels.to(device))
            total += float(loss) * len(x)
            count += len(x)
            predictions.append(prediction.cpu().numpy())
    return total / count, np.concatenate(predictions)


def report_policy(predictions, decisions, candles, config, output):
    signals, suggestions = [], []
    for prediction, row in zip(predictions, decisions.itertuples()):
        suggestion = decode_suggestion(prediction, row.close, row.atr, config)
        suggestions.append({"signal_time": str(row.signal_time), **suggestion})
        if suggestion["action"] != "WAIT":
            signals.append({"bar_index": row.bar_index, **suggestion})
    frame = pd.DataFrame(signals) if signals else pd.DataFrame(columns=["bar_index", "direction"])
    execution = ExecutionConfig(max_holding_bars=config["holding_bars"])
    result, trades = run_backtest(candles, frame, 100, CostModel(**config["costs"]), execution)
    stress_costs = dict(config["costs"], fee_rate_per_fill=0.00055)
    stress, _ = run_backtest(candles, frame, 100, CostModel(**stress_costs), execution)
    report = {"split": "validation_used_for_model_selection_NOT_test", "baseline_wait_final_equity": 100,
              "coverage": len(signals) / len(decisions), "decision_count": len(decisions),
              "result": asdict(result), "stress_fee_0_055_percent_per_fill": asdict(stress),
              "caveats": ["OHLC touch not maker queue", "market-like SL/timeout at scenario fees",
                          "uncalibrated win/fill scores", "close-sampled drawdown", "no leverage beyond 1x"]}
    (output / "validation_report.json").write_text(json.dumps(report, indent=2))
    (output / "validation_suggestions.json").write_text(json.dumps(suggestions, indent=2))
    pd.DataFrame([asdict(t) for t in trades]).to_csv(output / "validation_trades.csv", index=False)
    np.save(output / "validation_predictions.npy", predictions)
    return report


def train(args):
    started = time.monotonic()
    config = json.loads((args.dataset / "config.json").read_text())
    manifest = json.loads((args.dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(args.dataset / name) != digest:
            raise ValueError(f"Dataset hash mismatch: {name}")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    if args.require_two_t4 and (len(names) != 2 or not all("T4" in n for n in names)):
        raise RuntimeError(f"Expected T4 x2; got {names}. Stop rather than silently use another accelerator.")
    if args.output.exists():
        raise FileExistsError("Use a new output directory")
    args.output.mkdir(parents=True)
    seed = config["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.benchmark = False
    torch.set_num_threads(2)
    runtime = {"torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "gpus": names, "device": device,
               "encoder_parallelism": "DataParallel" if len(names) > 1 else "single",
               "training_stage": "frozen_Kronos_train_fusion_only", "seed": seed}
    (args.output / "runtime.json").write_text(json.dumps(runtime, indent=2))
    print(json.dumps(runtime), flush=True)
    encoder = KronosWindowEncoder(args.upstream, args.weights).to(device)
    width = encoder.backbone.d_model * 2
    if len(names) > 1:
        encoder = torch.nn.DataParallel(encoder)
    data = {}
    for split in ("train", "validation"):
        with np.load(args.dataset / f"{split}.npz", allow_pickle=False) as f:
            arrays = {k: f[k] for k in f.files}
        embeddings = encode(encoder, arrays, config["training"]["encode_batch_size"], device, split)
        data[split] = TensorDataset(embeddings, torch.from_numpy(arrays["ages"]), torch.from_numpy(arrays["labels"]))
    del encoder
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    # Fusion is tiny: train on GPU0. Both GPUs accelerate the expensive frozen trunk extraction.
    model = BracketFusion(width, config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["training"]["learning_rate"],
                                 weight_decay=config["training"]["weight_decay"])
    loaders = {name: DataLoader(value, batch_size=config["training"]["batch_size"], shuffle=name == "train")
               for name, value in data.items()}
    history, best, stale, best_epoch = [], float("inf"), 0, 0
    epochs = args.epochs or config["training"]["epochs"]
    for epoch in range(epochs):
        model.train()
        total, count = 0.0, 0
        for x, ages, labels in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            loss = trading_loss(model(x.to(device), ages.to(device)), labels.to(device))
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += float(loss.detach()) * len(x)
            count += len(x)
        val_loss, _ = validate(model, loaders["validation"], device)
        record = {"epoch": epoch + 1, "train_loss": total / count, "validation_loss": val_loss}
        history.append(record)
        print(json.dumps(record), flush=True)
        if val_loss < best:
            best, stale, best_epoch = val_loss, 0, epoch + 1
            save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
                      str(args.output / "fusion.safetensors"))
        else:
            stale += 1
        (args.output / "history.json").write_text(json.dumps(history, indent=2))
        if stale >= config["training"]["patience"]:
            break
    model.load_state_dict(load_file(str(args.output / "fusion.safetensors")))
    _, predictions = validate(model, loaders["validation"], device)
    decisions = pd.read_parquet(args.dataset / "validation_decisions.parquet")
    candles = pd.read_parquet(args.dataset / "development_candles.parquet")
    report = report_policy(predictions, decisions, candles, config, args.output)
    source_root = Path(__file__).resolve().parents[1]
    source_files = [Path(__file__), *sorted((source_root / "src").rglob("*.py"))]
    weights = {str(p.relative_to(args.weights)).replace("\\", "/"): sha256(p)
               for folder in ("Kronos-mini", "Kronos-Tokenizer-2k") for p in sorted((args.weights / folder).glob("*"))
               if p.name in ("config.json", "model.safetensors")}
    metadata = {"config": config, "encoder_width": width, "runtime": runtime, "best_epoch": best_epoch,
                "best_validation_loss": best, "elapsed_seconds": time.monotonic() - started,
                "dataset_manifest_sha256": sha256(args.dataset / "manifest.json"), "smoke_only": manifest["smoke_only"],
                "checkpoint_sha256": sha256(args.output / "fusion.safetensors"), "pretrained_weights": weights,
                "source_hashes": {str(p.relative_to(source_root)).replace("\\", "/"): sha256(p) for p in source_files},
                "upstream_hashes": {str(p.relative_to(args.upstream)).replace("\\", "/"): sha256(p)
                                    for p in sorted((args.upstream / "model").glob("*.py"))},
                "test_opened": False, "calibrated": False, "approved_for_live": False}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    parser.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--require-two-t4", action="store_true")
    train(parser.parse_args())
