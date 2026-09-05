"""Training/forecast export only. Portfolio evaluation deliberately stays local."""
import torch  # Must precede pandas on Windows.
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
from safetensors.torch import load_file, save_file
from agentic_alpha_lab.models.tcn_fusion_value import TemporalValue
from agentic_alpha_lab.models.temporal_value import predict
from agentic_alpha_lab.models.macro_micro_value import objective


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def fold_indices(decisions, parent, settings, fold):
    start, stop = map(pd.Timestamp, parent["folds"][fold])
    train = np.flatnonzero(((decisions.signal_time >= start - pd.Timedelta(days=settings["window_days"])) &
                           (decisions.label_end < start - pd.Timedelta(days=settings["embargo_days"]))).to_numpy())
    test = np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop) &
                          (decisions.label_end < pd.Timestamp(parent["complete_evaluation_until"]))).to_numpy())
    if len(train) < settings["minimum_train_decisions"] or not len(test) or np.intersect1d(train, test).size:
        raise ValueError("Invalid chronological fold")
    return train, test


def load_inputs(plan):
    dataset, cache = Path(plan["dataset"]), Path(plan["cache"])
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name in ("examples.npz", "decisions.parquet", "config.json"):
        if digest(dataset / name) != manifest["files"][name]:
            raise ValueError(f"Dataset hash mismatch: {name}")
    cm = json.loads((cache / "manifest.json").read_text())
    if cm["state"] != "complete" or cm["dataset_manifest_sha256"] != digest(dataset / "manifest.json"):
        raise ValueError("Cache identity mismatch")
    for name, expected in cm["files"].items():
        if digest(cache / name) != expected:
            raise ValueError(f"Cache hash mismatch: {name}")
    decisions = pd.read_parquet(dataset / "decisions.parquet")
    clock = pd.read_parquet(cache / "decisions.parquet")
    if not decisions.signal_time.equals(clock.signal_time):
        raise ValueError("Cache row alignment mismatch")
    if not decisions.signal_time.is_monotonic_increasing or decisions.signal_time.duplicated().any():
        raise ValueError("Invalid decision chronology")
    if not (decisions.label_end > decisions.signal_time).all():
        raise ValueError("Invalid label availability")
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    with np.load(dataset / "examples.npz", allow_pickle=False) as data:
        features, labels = data["features"], data["labels"]
    if sequence.shape != (len(decisions), 5, 128, 6) or features.shape != (len(decisions), 40) or labels.shape != (len(decisions), 16, 3):
        raise ValueError("Invalid dataset shapes")
    if not all(np.isfinite(x).all() for x in (sequence, features, labels)):
        raise ValueError("Nonfinite dataset")
    cfg = json.loads((dataset / "config.json").read_text())
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    return sequence, features, labels, decisions, candidates


def stable_evaluation_backend():
    # Avoid train/eval fused-MHA dispatch changes seen in v18 replay. Cross-device
    # numerical parity is still measured later, never assumed exact.
    torch.backends.mha.set_fastpath_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def run_fold(plan, parent, inputs, output, seed, fold):
    sequence, features, labels, decisions, candidates = inputs
    settings = plan["training"]
    train, test = fold_indices(decisions, parent, settings, fold)
    target = output / f"seed{seed}" / "checkpoints" / f"fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = TemporalValue(candidates, **plan["network"])
    model.feature_mean.copy_(torch.tensor(features[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(features[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    xs, xf, ys = [torch.tensor(x[train], dtype=torch.float32, device="cuda") for x in (sequence, features, labels)]
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"], weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    history = []
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    for epoch in range(settings["epochs"]):
        model.train()
        order = torch.randperm(len(train), device="cuda")
        total = 0.
        for group_start in range(0, len(order), effective):
            group = order[group_start:group_start + effective]
            optimizer.zero_grad(set_to_none=True)
            for start in range(0, len(group), batch):
                idx = group[start:start + batch]
                with torch.autocast("cuda", dtype=torch.float16, enabled=settings["amp"]):
                    score, aux = model(xs[idx], xf[idx])
                loss = objective(score.float(), aux.float(), ys[idx])
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite training loss")
                scaler.scale(loss * (len(idx) / len(group))).backward()
                total += loss.detach().item() * len(idx)
            scaler.unscale_(optimizer)
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
            if not torch.isfinite(norm) and not settings["amp"]:
                raise ValueError("Nonfinite gradients")
            scaler.step(optimizer)
            scaler.update()
        history.append(total / len(train))
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": history[-1]})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": history[-1]}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, test=test)
    details = {"seed": seed, "fold": fold, "network": plan["network"], "training": settings,
               "parameters": sum(p.numel() for p in model.parameters()), "training_loss": history,
               "train_decisions": len(train), "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "dataset_manifest_sha256": digest(Path(plan["dataset"]) / "manifest.json"),
               "cache_manifest_sha256": digest(Path(plan["cache"]) / "manifest.json"),
               "weights_sha256": digest(target / "model.safetensors"), "model_family": "tcn_fusion",
               "model_source_sha256": digest(Path(__file__).parents[1] / "src/agentic_alpha_lab/models/tcn_fusion_value.py"),
               "torch": torch.__version__, "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "gpu": torch.cuda.get_device_name(),
               "local_replay_required": True, "state": "weights_saved", "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict(model, sequence[test], features[test], batch_size=32)
    restored = TemporalValue(candidates, **plan["network"]).cuda()
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict(restored, sequence[test][:8], features[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.savez_compressed(target / "replay.npz", sequences=sequence[test][:8], features=features[test][:8], predictions=forecast[:8])
    pred_dir = output / f"seed{seed}" / "temporal_neural" / f"fold_{fold}"
    pred_dir.mkdir(parents=True)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite predictions")
    np.save(pred_dir / "predictions.npy", forecast)
    details.update(state="complete" if parity else "parity_failed", gpu_reload_parity=parity,
                   gpu_reload_max_error=float(np.max(np.abs(replay - forecast[:8]))),
                   prediction_sha256=digest(pred_dir / "predictions.npy"), elapsed_seconds=time.monotonic() - started)
    write_json(target / "metadata.json", details)
    print(json.dumps({"fold_saved": fold, "seed": seed, "state": details["state"], "seconds": details["elapsed_seconds"]}), flush=True)


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    if torch.cuda.device_count() != 1 or "T4" not in torch.cuda.get_device_name():
        raise RuntimeError("Worker requires one visible T4; no local heavy-training fallback")
    if not 0 <= a.shard < a.shards:
        raise ValueError("Invalid shard")
    plan = json.loads(a.plan.read_text())
    parent = json.loads(Path(plan["parent_plan"]).read_text())
    inputs = load_inputs(plan)
    jobs = [(seed, fold) for fold in range(len(parent["folds"])) for seed in plan["seeds"]]
    for job, (seed, fold) in enumerate(jobs):
        if job % a.shards == a.shard:
            run_fold(plan, parent, inputs, a.output, seed, fold)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--shards", type=int, default=2)
    main(parser.parse_args())
