"""Opencode R21-B cloud driver v55b (Kaggle PRIVATE T4, 1 GPU hien thi/worker).

Clone v55 driver (scripts/opencode_r17b_rankonly_train.py) VOI MOT thay doi duy
nhat: hard cap tanh CAP=3.0 tren rank logits TRUOC moi downstream:
  loss (ListNet tren capped, tau=1.0% co dinh, target KHONG DOI) +
  threshold-fit (p70 tren CAPPED val margins, past-only) +
  gate/policy + export (predictions.npy = CAPPED logits, |logit|<=3.0).

Walk-forward quarterly (11 folds) x seeds [1729,1730,1731], trailing 730d,
embargo 8d. FIXED 16 epochs (BO early-stop). Fit train past-only. Portfolio
chay LOCAL sau. GPU-agnostic guard: GPU la -> WARN va tiep tuc CPU, KHONG raise.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import copy
import hashlib
import json
import platform
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from safetensors.torch import load_file, save_file

from opencode_r21b_v55b_features import N_FLAT, build_flat
from opencode_r21b_v55b_model import (
    LOGIT_CAP,
    RANK_GATE_PERCENTILE,
    RANK_TEMPERATURE_PERCENT,
    RankOnlySSM,
    apply_rank_gate,
    cap_rank_logits_torch,
    count_params,
    listnet_rank_loss,
    predict_rank,
    rank_top1_margin_np,
)
from agentic_alpha_lab.models.temporal_validation import nested_split


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def stable_backend():
    torch.backends.mha.set_fastpath_enabled(False)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def resolve_device():
    """GPU-agnostic guard: T4 ly tuong; GPU la/CPU -> warn-and-continue (hoc tu A2)."""
    if torch.cuda.is_available():
        try:
            name = torch.cuda.get_device_name()
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Khong doc duoc ten GPU, fallback CPU: {exc}")
            return torch.device("cpu"), "cpu-unknown-gpu"
        if "T4" not in name:
            warnings.warn(f"GPU la '{name}' (khong phai T4) — warn-and-continue, khong raise (bai hoc A2).")
        return torch.device("cuda"), name
    warnings.warn("Khong co CUDA — chay CPU warn-and-continue (smoke/audit hoac GPU la).")
    return torch.device("cpu"), "cpu"


def make_model(plan, candidates):
    net = dict(plan["architecture"].get("frame_encoder", {}))
    d = {"frame_dim": net.get("d_model", 64), "frame_state": net.get("d_state", 16),
         "frame_layers": net.get("layers", 2),
         "cross_state": plan["architecture"].get("cross_frame", {}).get("d_state", 16),
         "dropout": plan["architecture"].get("dropout", 0.1)}
    return RankOnlySSM(candidates, n_flat=N_FLAT, **d)


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
    cfg = json.loads((ds / "config.json").read_text())
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    if candidates.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")
    return sequence, flat, labels, decisions, candidates


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
    sequence, flat, labels = arrays
    return (torch.tensor(sequence[ids], dtype=torch.float32, device=device),
            torch.tensor(flat[ids], dtype=torch.float32, device=device),
            torch.tensor(labels[ids], dtype=torch.float32, device=device))


def loss_params(plan):
    tr = plan.get("training", {})
    return (float(tr.get("ranking_temperature_percent", RANK_TEMPERATURE_PERCENT)),
            float(tr.get("gate_percentile", RANK_GATE_PERCENTILE)),
            float(tr.get("scale_cap_logit", LOGIT_CAP)))


def run_epoch(model, opt, scaler, arrays, ids, settings, tau, cap, dev, train_mode):
    use_amp = bool(settings["amp"]) and dev.type == "cuda" and train_mode
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    order = torch.randperm(len(ids), device=ids.device) if train_mode else torch.arange(len(ids), device=ids.device)
    total, count = 0.0, 0
    xs_all, xf_all, ys_all = arrays
    for left in range(0, len(order), effective):
        group = ids[order[left:left + effective]]
        if train_mode:
            opt.zero_grad(set_to_none=True)
        gtotal, gn = 0.0, 0
        for s in range(0, len(group), batch):
            ix = group[s:s + batch]
            with torch.autocast("cuda", enabled=use_amp):
                raw = model(xs_all[ix], xf_all[ix])
                logits = cap_rank_logits_torch(raw, cap)  # v55b: ONE change (cap truoc loss)
            loss = listnet_rank_loss(logits.float(), ys_all[ix], temperature_percent=tau)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            if train_mode:
                if scaler is not None:
                    scaler.scale(loss * (len(ix) / len(group))).backward()
                else:
                    (loss * (len(ix) / len(group))).backward()
            gtotal += loss.detach().item() * len(ix)
            gn += len(ix)
        if train_mode:
            if scaler is not None:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
                scaler.step(opt)
                scaler.update()
            else:
                torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
                opt.step()
        total += gtotal
        count += gn
    return total / count


def predict_capped(model, sequence, flat, cap, batch_size=32):
    """Export CAPPED rank logits (n,16), |logit| <= cap. (v55b export spec)."""
    import numpy as np  # noqa: F401
    from opencode_r21b_v55b_model import cap_rank_logits_np
    raw = predict_rank(model, sequence, flat, batch_size=batch_size)
    capped = cap_rank_logits_np(raw, cap)
    if not np.isfinite(capped).all():
        raise ValueError("Nonfinite capped rank logits")
    if not (np.abs(capped) <= cap + 1e-6).all():
        raise ValueError("Cap bound violated")
    return capped


def run_fold(plan, parent, inputs, output, seed, fold, dev):
    sequence, flat, labels, decisions, candidates = inputs
    settings = plan["training"]
    tau, gate_pct, cap = loss_params(plan)
    train, test = fold_indices(decisions, parent, plan, fold)
    spec = plan["epoch_selection"]
    _, validation, clock = nested_split(decisions, parent["folds"][fold][0],
                                        window_days=spec["window_days"],
                                        validation_days=spec["validation_days"],
                                        embargo_days=spec["embargo_days"],
                                        minimum_train=spec["minimum_train"],
                                        minimum_validation=spec["minimum_validation"])
    target = output / f"seed{seed}/checkpoints/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.to(dev)
    full = tensors_for(np.arange(len(decisions)), (sequence, flat, labels), dev)
    tid = torch.tensor(train, dtype=torch.int64, device=dev)
    vid = torch.tensor(validation, dtype=torch.int64, device=dev)
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=bool(settings["amp"]) and dev.type == "cuda")
    if dev.type == "cpu":
        scaler = None
    history, val_hist = [], []
    epochs = int(settings.get("epochs", settings.get("epochs_fixed", 16)))
    assert epochs == 16, f"v55b FIXED 16 epochs, nhan {epochs}"
    for epoch in range(epochs):
        model.train()
        tl = run_epoch(model, opt, scaler, full, tid, settings, tau, cap, dev, True)
        model.eval()
        with torch.no_grad():
            vl = run_epoch(model, None, None, full, vid, settings, tau, cap, dev, False)
        history.append(tl)
        val_hist.append(vl)
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1,
                                              "loss": tl, "val_loss": vl})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": tl,
                          "val_loss": vl}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, validation=validation, test=test)
    # Threshold gate: percentile dong bang tren CAPPED validation margins (past-only, causal).
    val_logits = predict_capped(model, sequence[validation], flat[validation], cap, batch_size=64)
    _, val_margins = rank_top1_margin_np(val_logits)
    threshold = float(np.percentile(val_margins, gate_pct))
    details = {"seed": seed, "fold": fold, "training": settings,
               "loss": {"only": "listnet_rank_loss", "ranking_temperature_percent": tau,
                        "heads": "rank-only (no value/dir/quant/exc/regime/fill/coverage)",
                        "scale_cap": {"mode": "tanh", "cap_logit": cap,
                                      "applies": "capped=logits truoc loss/gate/export"}},
               "rank_gate": {"percentile": gate_pct, "threshold_logit": threshold,
                             "threshold_basis": "CAPPED val margins (past-only)",
                             "val_margin_p50": float(np.percentile(val_margins, 50)),
                             "val_margin_p70": float(np.percentile(val_margins, 70)),
                             "val_margin_p90": float(np.percentile(val_margins, 90)),
                             "val_n": len(validation),
                             "rule": "top1 per decision IF capped-margin > threshold ELSE WAIT (no fallback)"},
               "epoch_mode": "FIXED 16 (no early-stop; validation monitor + gate-fit past-only)",
               "validation_clock": clock, "val_loss_by_epoch": val_hist,
               "parameters": count_params(model), "training_loss": history,
               "train_decisions": len(train), "validation_decisions": len(validation),
               "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "model_family": "rankonly_ssm_v55b", "torch": torch.__version__,
               "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "device": str(dev),
               "weights_sha256": digest(target / "model.safetensors"),
               "local_replay_required": True,
               "portfolio_next": "audit local: capped_logits_to_signals(test, threshold) -> signals -> replay/portfolio + monitor plan (pick-rate vs 30%)",
               "state": "weights_saved", "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict_capped(model, sequence[test], flat[test], cap, batch_size=64)
    assert forecast.shape == (len(test), 16)
    restored = make_model(plan, candidates).to(dev)
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict_capped(restored, sequence[test][:8], flat[test][:8], cap, batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.savez_compressed(target / "replay.npz", sequences=sequence[test][:8],
                        features=flat[test][:8], predictions=forecast[:8])
    pred_dir = output / f"seed{seed}/temporal_neural/fold_{fold}"
    pred_dir.mkdir(parents=True)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite predictions")
    np.save(pred_dir / "predictions.npy", forecast.astype(np.float32))
    test_top1, test_margins = rank_top1_margin_np(forecast)
    test_picks = apply_rank_gate(test_margins, threshold)
    details.update(state="complete" if parity else "parity_failed", gpu_reload_parity=parity,
                   gpu_reload_max_error=float(np.max(np.abs(replay - forecast[:8]))),
                   prediction_sha256=digest(pred_dir / "predictions.npy"),
                   test_gate_preview={"n_test": len(test), "n_picked": len(test_picks),
                                      "pick_rate": len(test_picks) / len(test),
                                      "expected_rate": 0.30,
                                      "monitor": "|pick_rate-0.30|>0.15 -> flag analysis-only (khong retrain)"},
                   elapsed_seconds=time.monotonic() - started)
    write_json(target / "metadata.json", details)
    print(json.dumps({"fold_saved": fold, "seed": seed, "state": details["state"]}), flush=True)


def main(a):
    torch.set_num_threads(2)
    stable_backend()
    dev, gpu_name = resolve_device()
    print(json.dumps({"device": str(dev), "gpu": gpu_name,
                      "guard": "warn-and-continue (khong raise tren GPU la/CPU)"}), flush=True)
    root = Path.cwd()
    plan = json.loads(a.plan.read_text())
    if plan.get("model_family") != "rankonly_ssm_v55b":
        raise ValueError("Unknown plan family for v55b driver")
    assert float(plan.get("architecture", {}).get("scale_cap", {}).get("cap_logit", -1)) == LOGIT_CAP
    tr = plan.get("training", {})
    epochs = int(tr.get("epochs", tr.get("epochs_fixed", 0)))
    assert epochs == 16, "v55b FIXED 16 epochs"
    assert float(tr.get("ranking_temperature_percent", -1)) == 1.0, "temperature phai 1.0"
    assert float(tr.get("gate_percentile", -1)) == 70.0, "gate percentile phai 70"
    assert float(tr.get("scale_cap_logit", -1)) == LOGIT_CAP, "cap phai 3.0"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v55b bo early-stop"
    assert plan.get("architecture", {}).get("heads_total") == 1, "v55b chi 1 head"
    assert int(plan["architecture"]["params_target"]["measured_parameters"]) == 597409
    parent = json.loads((root / plan["folds"]["parent"]).read_text())
    inputs = load_inputs(plan, root)
    jobs = [(seed, fold) for fold in range(len(parent["folds"])) for seed in plan["seeds"]]
    refit = copy.deepcopy(plan)
    for i, (seed, fold) in enumerate(jobs):
        if i % a.shards != a.shard:
            continue
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
        run_fold(refit, parent, inputs, a.output, seed, fold, dev)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=2)
    main(p.parse_args())
