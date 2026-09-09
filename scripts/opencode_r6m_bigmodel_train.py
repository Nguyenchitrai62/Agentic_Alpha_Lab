"""Opencode R6-M cloud driver (Kaggle PRIVATE T4, 1 GPU hien thi/worker).

Walk-forward quarterly (11 folds) x seeds [1729,1730,1731], trailing 730d,
embargo 8d. Nested validation past-only 180d chon epoch (patience 3,
cai thien toi thieu 1e-4, toi da 16 epochs), refit reset seed.
Loss DONG BANG: objective(score,aux,labels) + 1.0*CE_dir + 1.0*pinball P10/P50/P90
+ 0.5*MSE-log1p MFE/MAE (H=48, band 8bps). Export du bao map v8.
Portfolio evaluation KHONG chay tren cloud (local sau khi tai checkpoint).
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import copy
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
from safetensors.torch import load_file, save_file

from opencode_r6m_bigmodel_features import N_FLAT, build_flat
from opencode_r6m_bigmodel_model import BigTemporalMultitask, multitask_loss, predict_big
from agentic_alpha_lab.models.temporal_validation import earliest_best_epoch, nested_split

H = 48
BAND = 8e-4


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def stable_backend():
    torch.backends.mha.set_fastpath_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def load_inputs(plan, root):
    ds, cache = root / plan["dataset"], root / plan["cache"]
    manifest = json.loads((ds / "manifest.json").read_text())
    for name in ("examples.npz", "decisions.parquet", "config.json"):
        if digest(ds / name) != manifest["files"][name]:
            raise ValueError(f"Dataset hash mismatch: {name}")
    cm = json.loads((cache / "manifest.json").read_text())
    if cm["state"] != "complete" or cm["dataset_manifest_sha256"] != digest(ds / "manifest.json"):
        raise ValueError("Cache identity mismatch")
    for name, expected in cm["files"].items():
        if digest(cache / name) != expected:
            raise ValueError(f"Cache hash mismatch: {name}")
    decisions = pd.read_parquet(ds / "decisions.parquet")
    clock = pd.read_parquet(cache / "decisions.parquet")
    if not decisions.signal_time.equals(clock.signal_time):
        raise ValueError("Cache row alignment mismatch")
    if not decisions.signal_time.is_monotonic_increasing or decisions.signal_time.duplicated().any():
        raise ValueError("Invalid decision chronology")
    if not (decisions.label_end > decisions.signal_time).all():
        raise ValueError("Invalid label availability")
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    candles = pd.read_parquet(ds / "candles.parquet")
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      root / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      root / plan["funding_source"]["file"], root / plan["macro_source"]["dir"])
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels = z["labels"]
    if sequence.shape != (len(decisions), 5, 128, 6) or flat.shape != (len(decisions), N_FLAT):
        raise ValueError("Invalid input shapes")
    if labels.shape != (len(decisions), 16, 3):
        raise ValueError("Invalid label shapes")
    if not all(np.isfinite(x).all() for x in (sequence, flat, labels)):
        raise ValueError("Nonfinite inputs")
    c = candles["close"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    bi = decisions["bar_index"].to_numpy()
    if (bi + H + 1 >= len(c)).any():
        raise ValueError("Thieu tuong lai H=48")
    ret48 = (c[bi + H] / c[bi] - 1.0).astype(np.float64)
    up48 = np.clip(np.stack([h[bi + k] for k in range(1, H + 1)]).max(0) / c[bi] - 1.0, 0, None)
    dn48 = np.clip(1.0 - np.stack([low[bi + k] for k in range(1, H + 1)]).min(0) / c[bi], 0, None)
    ydir = np.select([ret48 < -BAND, ret48 > BAND], [0, 2], default=1).astype(np.int64)
    cfg = json.loads((ds / "config.json").read_text())
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    return sequence, flat, labels, ydir, ret48, up48, dn48, decisions, candidates


def fold_indices(decisions, parent, plan, fold):
    start, stop = map(pd.Timestamp, parent["folds"][fold])
    train = np.flatnonzero(((decisions.signal_time >= start - pd.Timedelta(days=plan["folds"]["trailing_window_days"])) &
                            (decisions.label_end < start - pd.Timedelta(days=plan["folds"]["embargo_days"]))).to_numpy())
    test = np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop) &
                           (decisions.label_end < pd.Timestamp(parent["complete_evaluation_until"]))).to_numpy())
    if len(train) < plan["folds"]["minimum_train_decisions"] or not len(test) or np.intersect1d(train, test).size:
        raise ValueError("Invalid chronological fold")
    return train, test


def select_epoch(plan, parent, inputs, output, seed, fold):
    sequence, flat, labels, ydir, ret48, up48, dn48, decisions, candidates = inputs
    spec = plan["epoch_selection"]
    keys = ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")
    train, validation, clock = nested_split(decisions, parent["folds"][fold][0],
                                            **{k: spec[k] for k in keys})
    target = output / f"seed{seed}/selection/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    xs = torch.tensor(sequence[train], dtype=torch.float32, device="cuda")
    xf = torch.tensor(flat[train], dtype=torch.float32, device="cuda")
    vs = torch.tensor(sequence[validation], dtype=torch.float32, device="cuda")
    vf = torch.tensor(flat[validation], dtype=torch.float32, device="cuda")
    ys = torch.tensor(labels[train], dtype=torch.float32, device="cuda")
    vy = torch.tensor(labels[validation], dtype=torch.float32, device="cuda")
    yd = torch.tensor(ydir[train], dtype=torch.int64, device="cuda")
    vyd = torch.tensor(ydir[validation], dtype=torch.int64, device="cuda")
    yr = torch.tensor(ret48[train], dtype=torch.float32, device="cuda")
    vyr = torch.tensor(ret48[validation], dtype=torch.float32, device="cuda")
    yu = torch.tensor(up48[train], dtype=torch.float32, device="cuda")
    vyu = torch.tensor(up48[validation], dtype=torch.float32, device="cuda")
    yn = torch.tensor(dn48[train], dtype=torch.float32, device="cuda")
    vyn = torch.tensor(dn48[validation], dtype=torch.float32, device="cuda")
    settings = plan["training"]
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    train_losses, validation_losses, scales = [], [], []
    selected, stale = None, 0
    for epoch in range(settings["epochs"]):
        model.train()
        order = torch.randperm(len(train), device="cuda")
        total = 0.
        for left in range(0, len(order), effective):
            group = order[left:left + effective]
            opt.zero_grad(set_to_none=True)
            for s in range(0, len(group), batch):
                ix = group[s:s + batch]
                with torch.autocast("cuda", dtype=torch.float16, enabled=settings["amp"]):
                    out = model(xs[ix], xf[ix])
                loss = multitask_loss(out[0].float(), out[1].float(), out[2].float(),
                                      out[3].float(), out[4].float(),
                                      ys[ix], yd[ix], yr[ix], yu[ix], yn[ix])
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite selection training loss")
                scaler.scale(loss * (len(ix) / len(group))).backward()
                total += loss.detach().item() * len(ix)
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
            scaler.step(opt)
            scaler.update()
        train_losses.append(total / len(train))
        model.eval()
        vtotal = 0.
        with torch.no_grad():
            for s in range(0, len(validation), batch):
                sl = slice(s, s + batch)
                vout = model(vs[sl], vf[sl])
                vtotal += multitask_loss(vout[0], vout[1], vout[2], vout[3], vout[4],
                                         vy[sl], vyd[sl], vyr[sl], vyu[sl], vyn[sl]).item() * (sl.stop - sl.start if sl.stop else 0)
        validation_losses.append(vtotal / len(validation))
        scales.append(float(scaler.get_scale()))
        best = earliest_best_epoch(validation_losses, spec["minimum_improvement"])
        if best != selected:
            selected, stale = best, 0
            save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
                      str(target / "selected.safetensors"))
        else:
            stale += 1
        print(json.dumps({"stage": "inner_selection", "seed": seed, "fold": fold, "epoch": epoch + 1,
                          "train_loss": train_losses[-1], "validation_loss": validation_losses[-1],
                          "selected_epoch": selected}), flush=True)
        if stale >= spec["patience"]:
            break
    record = {"seed": seed, "fold": fold, "selected_epoch": selected, "selection_spec": spec,
              "training_losses": train_losses, "validation_losses": validation_losses,
              "amp_scales": scales, "clock": clock,
              "selection_weights_sha256": digest(target / "selected.safetensors"),
              "rule": "Earliest validation-loss improvement; no outer labels or PnL.",
              "live_approved": False}
    np.savez_compressed(target / "indices.npz", train=train, validation=validation)
    write_json(target / "selection.json", record)
    return selected


def run_fold(plan, parent, inputs, output, seed, fold):
    sequence, flat, labels, ydir, ret48, up48, dn48, decisions, candidates = inputs
    settings = plan["training"]
    train, test = fold_indices(decisions, parent, plan, fold)
    target = output / f"seed{seed}/checkpoints/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    xs = torch.tensor(sequence[train], dtype=torch.float32, device="cuda")
    xf = torch.tensor(flat[train], dtype=torch.float32, device="cuda")
    ys = torch.tensor(labels[train], dtype=torch.float32, device="cuda")
    yd = torch.tensor(ydir[train], dtype=torch.int64, device="cuda")
    yr = torch.tensor(ret48[train], dtype=torch.float32, device="cuda")
    yu = torch.tensor(up48[train], dtype=torch.float32, device="cuda")
    yn = torch.tensor(dn48[train], dtype=torch.float32, device="cuda")
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    history = []
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    for epoch in range(settings["epochs"]):
        model.train()
        order = torch.randperm(len(train), device="cuda")
        total = 0.
        for left in range(0, len(order), effective):
            group = order[left:left + effective]
            opt.zero_grad(set_to_none=True)
            for s in range(0, len(group), batch):
                ix = group[s:s + batch]
                with torch.autocast("cuda", dtype=torch.float16, enabled=settings["amp"]):
                    out = model(xs[ix], xf[ix])
                loss = multitask_loss(out[0].float(), out[1].float(), out[2].float(),
                                      out[3].float(), out[4].float(),
                                      ys[ix], yd[ix], yr[ix], yu[ix], yn[ix])
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite training loss")
                scaler.scale(loss * (len(ix) / len(group))).backward()
                total += loss.detach().item() * len(ix)
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
            scaler.step(opt)
            scaler.update()
        history.append(total / len(train))
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": history[-1]})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": history[-1]}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, test=test)
    details = {"seed": seed, "fold": fold, "network": plan["architecture"]["network"],
               "training": settings,
               "parameters": sum(p.numel() for p in model.parameters()), "training_loss": history,
               "train_decisions": len(train), "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "model_family": "bigmodel_tcn_multitask", "torch": torch.__version__,
               "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "gpu": torch.cuda.get_device_name(),
               "weights_sha256": digest(target / "model.safetensors"),
               "local_replay_required": True, "state": "weights_saved", "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict_big(model, sequence[test], flat[test], batch_size=32)
    restored = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT).cuda()
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict_big(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.savez_compressed(target / "replay.npz", sequences=sequence[test][:8],
                        features=flat[test][:8], predictions=forecast[:8])
    pred_dir = output / f"seed{seed}/temporal_neural/fold_{fold}"
    pred_dir.mkdir(parents=True)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite predictions")
    np.save(pred_dir / "predictions.npy", forecast)
    details.update(state="complete" if parity else "parity_failed", gpu_reload_parity=parity,
                   gpu_reload_max_error=float(np.max(np.abs(replay - forecast[:8]))),
                   prediction_sha256=digest(pred_dir / "predictions.npy"),
                   elapsed_seconds=time.monotonic() - started)
    write_json(target / "metadata.json", details)
    print(json.dumps({"fold_saved": fold, "seed": seed, "state": details["state"]}), flush=True)


def main(a):
    torch.set_num_threads(2)
    stable_backend()
    if torch.cuda.device_count() != 1 or "T4" not in torch.cuda.get_device_name():
        raise RuntimeError("Worker requires one visible T4; no local heavy-training fallback")
    root = Path.cwd()
    plan = json.loads(a.plan.read_text())
    parent = json.loads((root / plan["folds"]["parent"]).read_text())
    inputs = load_inputs(plan, root)
    jobs = [(seed, fold) for fold in range(len(parent["folds"])) for seed in plan["seeds"]]
    for i, (seed, fold) in enumerate(jobs):
        if i % a.shards != a.shard:
            continue
        epoch = select_epoch(plan, parent, inputs, a.output, seed, fold)
        refit = copy.deepcopy(plan)
        refit["training"]["epochs"] = epoch
        torch.cuda.empty_cache()
        run_fold(refit, parent, inputs, a.output, seed, fold)
        target = a.output / f"seed{seed}/checkpoints/fold_{fold}/metadata.json"
        meta = json.loads(target.read_text())
        meta["selection_record_sha256"] = digest(a.output / f"seed{seed}/selection/fold_{fold}/selection.json")
        meta["epoch_selection"] = plan["epoch_selection"]
        write_json(target, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=2)
    main(p.parse_args())
