"""DDP full-trunk Kronos-base swing training. One bounded, versioned experiment."""
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import TensorDataset, DataLoader, DistributedSampler
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import platform
import random
import time
import numpy as np
import pandas as pd
from safetensors.torch import save_file, load_file
from agentic_alpha_lab.models.swing import SwingKronos, swing_loss
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import evaluate

KEYS = ("windows", "stamps", "ages", "features", "labels", "auxiliary")


def read_arrays(path, limit=None):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k][:limit] if limit else f[k] for k in KEYS}


def loader(arrays, batch, sampler=None, shuffle=False):
    dataset = TensorDataset(*(torch.from_numpy(arrays[k]) for k in KEYS))
    return DataLoader(dataset, batch_size=batch, sampler=sampler, shuffle=shuffle and sampler is None)


def predict(model, arrays, batch, device):
    model.eval()
    total, count, outputs = 0., 0, []
    with torch.no_grad():
        for tensors in loader(arrays, batch):
            tensors = [t.to(device) for t in tensors]
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                p, aux = model(*tensors[:4])
                loss = swing_loss(p, aux, *tensors[4:])
            total += float(loss) * len(p)
            count += len(p)
            outputs.append(p.float().cpu().numpy())
    return total / count, np.concatenate(outputs)


def train(a):
    started = time.monotonic()
    rank, world, local = int(os.getenv("RANK", 0)), int(os.getenv("WORLD_SIZE", 1)), int(os.getenv("LOCAL_RANK", 0))
    config = json.loads((a.dataset / "config.json").read_text())
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Data hash mismatch: {name}")
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    if a.require_two_t4 and (world != 2 or len(names) != 2 or not all("T4" in n for n in names)):
        raise RuntimeError(f"Expected DDP on T4 x2: world={world}, devices={names}")
    device = torch.device(a.device if a.device else f"cuda:{local}" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        torch.cuda.set_device(device)
    if world > 1:
        dist.init_process_group("nccl")
    torch.set_num_threads(2)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    if rank == 0:
        if a.output.exists():
            raise FileExistsError("Use a new run directory")
        a.output.mkdir(parents=True)
    if world > 1:
        dist.barrier()
    arrays = read_arrays(a.dataset / "train.npz", 2 if a.smoke else None)
    dataset = TensorDataset(*(torch.from_numpy(arrays[k]) for k in KEYS))
    sampler = DistributedSampler(dataset, num_replicas=world, rank=rank, seed=config["seed"]) if world > 1 else None
    training = loader(arrays, config["training"]["batch_per_gpu"], sampler, True)
    del arrays
    model = SwingKronos(a.upstream, a.weights, config).to(device)
    initial = [next(b.parameters()).detach().flatten()[:1024].cpu().clone() for b in model.blocks]
    backbone_names = ("embedding.", "time_emb.", "blocks.", "norm.")
    groups = [{"params": [p for n, p in model.named_parameters() if p.requires_grad and n.startswith(backbone_names)],
               "lr": config["training"]["backbone_lr"]},
              {"params": [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith(backbone_names)],
               "lr": config["training"]["head_lr"]}]
    optimizer = torch.optim.AdamW(groups, weight_decay=config["training"]["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", init_scale=1024, enabled=device.type == "cuda")
    wrapped = DDP(model, device_ids=[local]) if world > 1 else model
    runtime = {"torch": torch.__version__, "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
               "gpus": names, "world_size": world, "precision": "fp16 AMP" if device.type == "cuda" else "fp32",
               "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
               "frozen_tokenizer_parameters": sum(p.numel() for p in model.tokenizer.parameters()),
               "trainable_kronos_blocks": len(model.blocks), "architecture": config["schema"], "smoke": a.smoke}
    if rank == 0:
        print(json.dumps(runtime), flush=True)
        (a.output / "runtime.json").write_text(json.dumps(runtime, indent=2))
    history, best, stale, best_epoch, block_grads = [], float("inf"), 0, 0, []
    epochs = 1 if a.smoke else config["training"]["epochs"]
    accumulation = 1 if a.smoke else config["training"]["accumulation"]
    for epoch in range(epochs):
        if sampler:
            sampler.set_epoch(epoch)
        wrapped.train()
        optimizer.zero_grad(set_to_none=True)
        total, count, timed_out = 0., 0, False
        for step, tensors in enumerate(training):
            sync = (step + 1) % accumulation == 0 or step + 1 == len(training)
            group_size = min(accumulation, len(training) - (step // accumulation) * accumulation)
            tensors = [t.to(device) for t in tensors]
            with (wrapped.no_sync() if world > 1 and not sync else nullcontext()):
                with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                    prediction, aux = wrapped(*tensors[:4])
                    loss = swing_loss(prediction, aux, *tensors[4:])
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite loss")
                scaler.scale(loss / group_size).backward()
            total += float(loss.detach()) * len(tensors[0])
            count += len(tensors[0])
            if sync:
                scaler.unscale_(optimizer)
                if not block_grads:
                    block_grads = [sum(float(p.grad.float().abs().sum()) for p in b.parameters() if p.grad is not None) for b in model.blocks]
                    if not all(np.isfinite(g) and g > 0 for g in block_grads):
                        # GradScaler will skip overflowed steps and lower its scale.
                        block_grads = []
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                flag = torch.tensor(int(time.monotonic() - started > config["training"]["max_seconds"]), device=device)
                if world > 1:
                    dist.all_reduce(flag, op=dist.ReduceOp.MAX)
                if flag.item():
                    timed_out = True
                    break
            if rank == 0 and step % 100 == 0:
                print(f"epoch {epoch+1}, batch {step+1}/{len(training)}, loss {float(loss.detach()):.5f}", flush=True)
        stats = torch.tensor([total, count], device=device, dtype=torch.float64)
        if world > 1:
            dist.all_reduce(stats)
        if rank == 0:
            val_arrays = read_arrays(a.dataset / "validation.npz", 2 if a.smoke else None)
            val_loss, _ = predict(model, val_arrays, 2, device)
            del val_arrays
            if not np.isfinite(val_loss):
                raise ValueError("Non-finite validation loss")
            record = {"epoch": epoch+1, "train_loss": float(stats[0] / stats[1]), "validation_loss": val_loss,
                      "partial_epoch": timed_out, "elapsed_seconds": time.monotonic() - started}
            history.append(record)
            print(json.dumps(record), flush=True)
            if val_loss < best:
                best, stale, best_epoch = val_loss, 0, epoch+1
                save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(a.output / "swing.safetensors"))
            else:
                stale += 1
            (a.output / "history.json").write_text(json.dumps(history, indent=2))
        stop = torch.tensor(int(timed_out or stale >= config["training"]["patience"]), device=device)
        if world > 1:
            dist.broadcast(stop, 0)
        if stop.item():
            break
    if world > 1:
        dist.barrier()
    if rank == 0:
        model.load_state_dict(load_file(str(a.output / "swing.safetensors")))
        del optimizer, wrapped
        if device.type == "cuda":
            torch.cuda.empty_cache()
        deltas = [float((next(b.parameters()).detach().flatten()[:1024].cpu() - before).abs().max())
                  for b, before in zip(model.blocks, initial)]
        if not all(d > 0 for d in deltas):
            raise ValueError(f"Some pretrained blocks did not update: {deltas}")
        for split in ("validation", "policy"):
            data = read_arrays(a.dataset / f"{split}.npz", 2 if a.smoke else None)
            _, predictions = predict(model, data, 2, device)
            decisions = pd.read_parquet(a.dataset / f"{split}_decisions.parquet").iloc[:len(predictions)]
            report, signals, trades = evaluate(predictions, decisions, pd.read_parquet(a.dataset / "development_candles.parquet"), config, split)
            np.save(a.output / f"{split}_predictions.npy", predictions)
            signals.to_parquet(a.output / f"{split}_signals.parquet", index=False)
            trades.to_csv(a.output / f"{split}_trades.csv", index=False)
            (a.output / f"{split}_report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
        root = Path(__file__).resolve().parents[1]
        source_files = [Path(__file__), *sorted((root / "src").rglob("*.py"))]
        meta = {"config": config, "runtime": runtime, "best_epoch": best_epoch, "best_validation_loss": best,
                "checkpoint_sha256": sha256(a.output / "swing.safetensors"), "dataset_manifest_sha256": sha256(a.dataset / "manifest.json"),
                "full_trunk_updated": True, "first_step_block_gradient_l1": block_grads, "best_block_weight_delta_probe": deltas,
                "elapsed_seconds": time.monotonic() - started, "test_evaluated": False, "approved_for_live": False,
                "source_hashes": {p.relative_to(root).as_posix(): sha256(p) for p in source_files},
                "upstream_hashes": {p.relative_to(a.upstream).as_posix(): sha256(p) for p in sorted((a.upstream / "model").glob("*.py"))},
                "initial_weights": {p.relative_to(a.weights).as_posix(): sha256(p)
                    for folder in ("Kronos-base", "Kronos-Tokenizer-base") for p in (a.weights / folder).glob("*")
                    if p.name in ("config.json", "model.safetensors")}}
        (a.output / "metadata.json").write_text(json.dumps(meta, indent=2))
        print("FULL_TRUNK_FINETUNE_COMPLETE", flush=True)
    if world > 1:
        dist.barrier()
        dist.destroy_process_group()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    p.add_argument("--require-two-t4", action="store_true")
    p.add_argument("--smoke", action="store_true")
    train(p.parse_args())
