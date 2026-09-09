"""Opencode R25-M cloud driver v40 (Kaggle PRIVATE T4, 1 GPU hien thi/worker).

Walk-forward quarterly (11 folds) x seeds [1729,1730,1731], trailing 730d,
embargo 8d. FIXED 16 epochs (GIU tu v38/v39). Fit train/val past-only (mean/std chi
fit tren train-window; nested-validation 180d giam sat + EXPORT val-predictions
de calibrate-first outlier-robust THAT o audit local sau, KHONG chon epoch,
KHONG tune theo PnL).
Loss DONG BANG configs/opencode_v77_v40.json (GIONG v38, SUA v39):
  2.0*objective(score_raw,aux,labels) + 0.5*pairwise-ranking(value head RAW
  tanh-free, temperature 1.0%, tie-band 0.25%, nhu v29/v38) + 1.0*CE_dir
  + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48, band 8bps)
  + 3.0*coverage-hinge (TREN RAW).
Cap CHI o policy/export (clip +-2% post-hoc, eval-only, khong gradient).
Tie-break deterministic (eps 1e-6, fill-desc, holding-asc) o policy.
Export du bao CAPPED map v8: test predictions + VAL predictions (ke thua v39,
sua blocker v38: cloud chi export test -> khong the calibrate-that).
Portfolio + calibrate-first (outlier-robust) chay LOCAL sau.
GPU-agnostic guard (hoc tu A2 P100 sm_60): GPU la -> WARN va tiep tuc CPU,
KHONG raise tu huy.
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

from opencode_r25m_v40_features import N_FLAT, build_flat
from opencode_r25m_v40_model import (
    COV_FLOOR_POS,
    COV_LAMBDA,
    LOSS_W_RANK,
    LOSS_W_VALUE,
    POLICY_CAP,
    POLICY_CAP_MODE,
    RANK_TEMP_PCT,
    RANK_TIE_PCT,
    TIE_BREAK_EPS,
    CapAtPolicySSMTemporal,
    count_params,
    multitask_loss_cov_rank,
    predict_ssm,
)
from agentic_alpha_lab.models.temporal_validation import nested_split

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
    return CapAtPolicySSMTemporal(candidates, n_flat=N_FLAT, **d)


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


def loss_params(plan):
    tr = plan.get("training", {})
    if str(tr.get("policy_cap_mode", "clip")) != "clip":
        raise ValueError("v40 policy_cap_mode phai clip")
    if float(tr.get("policy_cap_cap", -1)) != POLICY_CAP:
        raise ValueError("v40 policy_cap_cap phai 0.02")
    if float(tr.get("tie_break_eps", -1)) != TIE_BREAK_EPS:
        raise ValueError("v40 tie_break_eps phai 1e-6")
    if "scale_cap_cap" in tr or "scale_cap_mode" in tr:
        raise ValueError("v40 KHONG co scale_cap trong loss (cap-at-policy only)")
    return (float(tr.get("value_weight", LOSS_W_VALUE)),
            float(tr.get("ranking_weight", LOSS_W_RANK)),
            float(tr.get("coverage_lambda", COV_LAMBDA)),
            float(tr.get("coverage_floor_pos", COV_FLOOR_POS)),
            float(tr.get("ranking_temperature_percent", RANK_TEMP_PCT)),
            float(tr.get("ranking_tie_band_percent", RANK_TIE_PCT)))


def run_epoch(model, opt, scaler, arrays, ids, settings, lp, dev, train_mode):
    vw, rw, lam, flr, rtemp, rtie = lp
    use_amp = bool(settings["amp"]) and dev.type == "cuda" and train_mode
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    order = torch.randperm(len(ids), device=ids.device) if train_mode else torch.arange(len(ids), device=ids.device)
    total, rank_acc, cov_acc, pos_acc, count = 0.0, 0.0, 0.0, 0.0, 0
    xs_all, xf_all, ys_all, yd_all, yr_all, yu_all, yn_all = arrays
    for left in range(0, len(order), effective):
        group = ids[order[left:left + effective]]
        if train_mode:
            opt.zero_grad(set_to_none=True)
        gtotal, gn = 0.0, 0
        for s in range(0, len(group), batch):
            ix = group[s:s + batch]
            with torch.autocast("cuda", enabled=use_amp):
                out = model(xs_all[ix], xf_all[ix])
            loss, parts = multitask_loss_cov_rank(
                out[0].float(), out[1].float(), out[2].float(),
                out[3].float(), out[4].float(),
                ys_all[ix], yd_all[ix], yr_all[ix], yu_all[ix], yn_all[ix],
                value_w=vw, rank_w=rw, lambda_cov=lam, floor_pos=flr,
                rank_temp=rtemp, rank_tie=rtie)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            if train_mode:
                if scaler is not None:
                    scaler.scale(loss * (len(ix) / len(group))).backward()
                else:
                    (loss * (len(ix) / len(group))).backward()
            gtotal += loss.detach().item() * len(ix)
            rank_acc += float(parts["rank"]) * len(ix)
            cov_acc += float(parts["cov"]) * len(ix)
            pos_acc += float(parts["mean_pos"]) * len(ix)
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
    return total / count, rank_acc / count, cov_acc / count, pos_acc / count


def run_fold(plan, parent, inputs, output, seed, fold, dev):
    sequence, flat, labels, ydir, ret48, up48, dn48, decisions, candidates = inputs
    settings = plan["training"]
    lp = loss_params(plan)
    train, test = fold_indices(decisions, parent, plan, fold)
    # Nested validation past-only: giam sat + EXPORT val-predictions de calibrate-first
    # outlier-robust THAT o audit sau.
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
    if not isinstance(model, CapAtPolicySSMTemporal):
        raise ValueError("v40 model phai la CapAtPolicySSMTemporal (RAW, cap post-hoc)")
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.to(dev)
    full = tensors_for(np.arange(len(decisions)), (sequence, flat, labels, ydir, ret48, up48, dn48), dev)
    tid = torch.tensor(train, dtype=torch.int64, device=dev)
    vid = torch.tensor(validation, dtype=torch.int64, device=dev)
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=bool(settings["amp"]) and dev.type == "cuda")
    if dev.type == "cpu":
        scaler = None
    history, rank_hist, cov_hist, pos_hist, val_hist = [], [], [], [], []
    epochs = int(settings["epochs"])
    assert epochs == 16, f"v40 FIXED 16 epochs, nhan {epochs}"
    for epoch in range(epochs):
        model.train()
        tl, tr_, tc, tp = run_epoch(model, opt, scaler, full, tid, settings, lp, dev, True)
        model.eval()
        with torch.no_grad():
            vl, vr, vc, vp = run_epoch(model, None, None, full, vid, settings, lp, dev, False)
        history.append(tl)
        rank_hist.append(tr_)
        cov_hist.append(tc)
        pos_hist.append(tp)
        val_hist.append(vl)
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1,
                                              "loss": tl, "rank": tr_, "cov": tc,
                                              "mean_pos": tp, "val_loss": vl})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": tl,
                          "rank": tr_, "cov": tc, "mean_pos": tp, "val_loss": vl}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, validation=validation, test=test)
    details = {"seed": seed, "fold": fold, "training": settings,
               "loss": {"value_weight": lp[0], "ranking_weight": lp[1],
                        "ranking_temperature_percent": lp[4],
                        "ranking_tie_band_percent": lp[5],
                        "coverage": {"lambda": lp[2], "floor_pos": lp[3], "domain": "RAW"},
                        "policy_cap": {"mode": POLICY_CAP_MODE, "cap": POLICY_CAP,
                                       "applies_to": "policy/export only (post-hoc clip, no gradient)"},
                        "tie_break": {"eps": TIE_BREAK_EPS,
                                      "rule": "gap<1e-6 -> fill-desc, holding-asc, index-min"}},
               "coverage": {"lambda": lp[2], "floor_pos": lp[3],
                            "train_cov_by_epoch": cov_hist, "train_mean_pos_by_epoch": pos_hist},
               "epoch_mode": "FIXED 16 (no early-stop; validation monitor-only past-only + export)",
               "validation_clock": clock, "val_loss_by_epoch": val_hist,
               "rank_by_epoch": rank_hist,
               "parameters": count_params(model), "training_loss": history,
               "train_decisions": len(train), "validation_decisions": len(validation),
               "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "model_family": "capatpolicy_selective_ssm_v40", "torch": torch.__version__,
               "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "device": str(dev),
               "weights_sha256": digest(target / "model.safetensors"),
               "local_replay_required": True,
               "calibration_next": "audit local: fit isotonic outlier-robust tren VAL-PRED EXPORT (val_predictions.npy, CAPPED clip +-2%) past-only TRUOC choose, nguong tu phan vi validation, tie-break deterministic",
               "state": "weights_saved", "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict_ssm(model, sequence[test], flat[test], batch_size=32)
    # v40: export validation predictions CAPPED (cung model FIXED-epoch) de calibrate-first THAT.
    val_forecast = predict_ssm(model, sequence[validation], flat[validation], batch_size=32)
    restored = make_model(plan, candidates).to(dev)
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict_ssm(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.savez_compressed(target / "replay.npz", sequences=sequence[test][:8],
                        features=flat[test][:8], predictions=forecast[:8])
    pred_dir = output / f"seed{seed}/temporal_neural/fold_{fold}"
    pred_dir.mkdir(parents=True)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite test predictions")
    if not np.isfinite(val_forecast).all():
        raise ValueError("Nonfinite validation predictions")
    if val_forecast.shape != (len(validation), 16, 6):
        raise ValueError("Invalid validation prediction shape")
    np.save(pred_dir / "predictions.npy", forecast)
    np.save(pred_dir / "val_predictions.npy", val_forecast)
    details.update(state="complete" if parity else "parity_failed", gpu_reload_parity=parity,
                   gpu_reload_max_error=float(np.max(np.abs(replay - forecast[:8]))),
                   prediction_sha256=digest(pred_dir / "predictions.npy"),
                   val_prediction_sha256=digest(pred_dir / "val_predictions.npy"),
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
    if plan.get("model_family") != "capatpolicy_selective_ssm_v40":
        raise ValueError("Unknown plan family for v40 driver")
    tr = plan.get("training", {})
    assert int(tr.get("epochs", 0)) == 16, "v40 FIXED 16 epochs"
    assert float(tr.get("ranking_weight", -1)) == 0.5, "ranking_weight phai 0.5"
    assert float(tr.get("value_weight", -1)) == 2.0, "value_weight phai 2.0"
    assert str(tr.get("policy_cap_mode", "")) == "clip", "v40 policy_cap_mode phai clip"
    assert float(tr.get("policy_cap_cap", -1)) == 0.02, "v40 policy_cap_cap phai 0.02"
    assert float(tr.get("tie_break_eps", -1)) == 1e-6, "v40 tie_break_eps phai 1e-6"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v40 bo early-stop"
    assert float(plan.get("budget", {}).get("gpu_hours_max", 99)) <= 10.0, "budget tran 10 GPU-gio"
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
