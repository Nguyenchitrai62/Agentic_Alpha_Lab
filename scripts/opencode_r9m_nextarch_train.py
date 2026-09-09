"""Opencode R9-M cloud driver v35 (Kaggle PRIVATE T4, 1 GPU hien thi/worker).

Walk-forward quarterly (11 folds) x seeds [1729,1730,1731], trailing 730d,
embargo 8d. Nested validation past-only 180d chon epoch bang FULL loss
(GOM coverage-hinge) — patience 3, cai thien toi thieu 1e-4, toi da 12 epochs.
Loss DONG BANG configs/opencode_v35_nextarch.json:
  objective(score,aux,labels) + 1.0*CE_dir + 1.0*pinball P10/P50/P90
  + 0.5*MSE-log1p MFE/MAE (H=48, band 8bps) + 3.0*coverage-hinge.
Export du bao map v8. Portfolio evaluation KHONG chay tren cloud.
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

from opencode_r9m_nextarch_features import N_FLAT, build_flat
from opencode_r9m_nextarch_model import (
    COV_FLOOR_POS,
    COV_LAMBDA,
    SelectiveSSMTemporal,
    count_params,
    multitask_loss_cov,
    predict_ssm,
)
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


def make_model(plan, candidates):
    net = dict(plan["architecture"].get("frame_encoder", {}))
    d = {"frame_dim": net.get("d_model", 64), "frame_state": net.get("d_state", 16),
         "frame_layers": net.get("layers", 2),
         "cross_state": plan["architecture"].get("cross_frame", {}).get("d_state", 16),
         "dropout": plan["architecture"].get("dropout", 0.1)}
    return SelectiveSSMTemporal(candidates, n_flat=N_FLAT, **d)


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


def tensors_for(ids, arrays, device):
    sequence, flat, labels, ydir, ret48, up48, dn48 = arrays
    return (torch.tensor(sequence[ids], dtype=torch.float32, device=device),
            torch.tensor(flat[ids], dtype=torch.float32, device=device),
            torch.tensor(labels[ids], dtype=torch.float32, device=device),
            torch.tensor(ydir[ids], dtype=torch.int64, device=device),
            torch.tensor(ret48[ids], dtype=torch.float32, device=device),
            torch.tensor(up48[ids], dtype=torch.float32, device=device),
            torch.tensor(dn48[ids], dtype=torch.float32, device=device))


def cov_params(plan):
    tr = plan.get("training", {})
    return float(tr.get("coverage_lambda", COV_LAMBDA)), float(tr.get("coverage_floor_pos", COV_FLOOR_POS))


def run_epoch(model, opt, scaler, arrays, ids, settings, lam, flr, train_mode):
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    order = torch.randperm(len(ids), device=ids.device) if train_mode else torch.arange(len(ids), device=ids.device)
    total, cov_acc, pos_acc, count = 0.0, 0.0, 0.0, 0
    xs_all, xf_all, ys_all, yd_all, yr_all, yu_all, yn_all = arrays
    for left in range(0, len(order), effective):
        group = ids[order[left:left + effective]]
        if train_mode:
            opt.zero_grad(set_to_none=True)
        gtotal, gn = 0.0, 0
        for s in range(0, len(group), batch):
            ix = group[s:s + batch]
            with torch.autocast("cuda", enabled=settings["amp"] and train_mode):
                out = model(xs_all[ix], xf_all[ix])
            loss, parts = multitask_loss_cov(out[0].float(), out[1].float(), out[2].float(),
                                             out[3].float(), out[4].float(),
                                             ys_all[ix], yd_all[ix], yr_all[ix], yu_all[ix], yn_all[ix],
                                             lam, flr)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            if train_mode:
                scaler.scale(loss * (len(ix) / len(group))).backward()
            gtotal += loss.detach().item() * len(ix)
            cov_acc += float(parts["cov"]) * len(ix)
            pos_acc += float(parts["mean_pos"]) * len(ix)
            gn += len(ix)
        if train_mode:
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
            scaler.step(opt)
            scaler.update()
        total += gtotal
        count += gn
    return total / count, cov_acc / count, pos_acc / count


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
    lam, flr = cov_params(plan)
    model = make_model(plan, candidates)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    dev = torch.device("cuda")
    full = tensors_for(np.arange(len(decisions)), (sequence, flat, labels, ydir, ret48, up48, dn48), dev)
    tid = torch.tensor(train, dtype=torch.int64, device=dev)
    vid = torch.tensor(validation, dtype=torch.int64, device=dev)
    settings = plan["training"]
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    train_losses, validation_losses, mean_poss, scales = [], [], [], []
    selected, stale = None, 0
    for epoch in range(settings["epochs"]):
        model.train()
        tl, _, tpos = run_epoch(model, opt, scaler, full, tid, settings, lam, flr, True)
        model.eval()
        with torch.no_grad():
            vl, vcov, vpos = run_epoch(model, None, None, full, vid, settings, lam, flr, False)
        train_losses.append(tl)
        validation_losses.append(vl)
        mean_poss.append(vpos)
        scales.append(float(scaler.get_scale()))
        best = earliest_best_epoch(validation_losses, spec["minimum_improvement"])
        if best != selected:
            selected, stale = best, 0
            save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
                      str(target / "selected.safetensors"))
        else:
            stale += 1
        print(json.dumps({"stage": "inner_selection", "seed": seed, "fold": fold, "epoch": epoch + 1,
                          "train_loss": tl, "validation_loss": vl, "val_cov": vcov,
                          "val_mean_pos": vpos, "selected_epoch": selected}), flush=True)
        if stale >= spec["patience"]:
            break
    record = {"seed": seed, "fold": fold, "selected_epoch": selected, "selection_spec": spec,
              "coverage": {"lambda": lam, "floor_pos": flr, "val_mean_pos_by_epoch": mean_poss},
              "training_losses": train_losses, "validation_losses": validation_losses,
              "amp_scales": scales, "clock": clock,
              "selection_weights_sha256": digest(target / "selected.safetensors"),
              "rule": "Earliest FULL validation-loss (gom coverage-hinge) improvement; no outer labels or PnL.",
              "live_approved": False}
    np.savez_compressed(target / "indices.npz", train=train, validation=validation)
    write_json(target / "selection.json", record)
    return selected


def run_fold(plan, parent, inputs, output, seed, fold):
    sequence, flat, labels, ydir, ret48, up48, dn48, decisions, candidates = inputs
    settings = plan["training"]
    lam, flr = cov_params(plan)
    train, test = fold_indices(decisions, parent, plan, fold)
    target = output / f"seed{seed}/checkpoints/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    dev = torch.device("cuda")
    full = tensors_for(np.arange(len(decisions)), (sequence, flat, labels, ydir, ret48, up48, dn48), dev)
    tid = torch.tensor(train, dtype=torch.int64, device=dev)
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    history, cov_hist, pos_hist = [], [], []
    for epoch in range(settings["epochs"]):
        model.train()
        tl, tc, tp = run_epoch(model, opt, scaler, full, tid, settings, lam, flr, True)
        history.append(tl)
        cov_hist.append(tc)
        pos_hist.append(tp)
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1,
                                              "loss": tl, "cov": tc, "mean_pos": tp})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": tl,
                          "cov": tc, "mean_pos": tp}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, test=test)
    details = {"seed": seed, "fold": fold, "training": settings,
               "coverage": {"lambda": lam, "floor_pos": flr,
                            "train_cov_by_epoch": cov_hist, "train_mean_pos_by_epoch": pos_hist},
               "parameters": count_params(model), "training_loss": history,
               "train_decisions": len(train), "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "model_family": "nextarch_selective_ssm_v35", "torch": torch.__version__,
               "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "gpu": torch.cuda.get_device_name(),
               "weights_sha256": digest(target / "model.safetensors"),
               "local_replay_required": True, "state": "weights_saved", "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict_ssm(model, sequence[test], flat[test], batch_size=32)
    restored = make_model(plan, candidates).cuda()
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict_ssm(restored, sequence[test][:8], flat[test][:8], batch_size=32)
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
    if plan.get("model_family") != "nextarch_selective_ssm_v35":
        raise ValueError("Unknown plan family for v35 driver")
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
