"""Opencode R37-M cloud driver v106 (Kaggle PRIVATE T4, 1 GPU hien thi/worker).

Walk-forward quarterly (11 folds) x seeds [1729,1730,1731], trailing 730d,
embargo 8d. FIXED 16 epochs (GIU tu v38/v39/v40/v41). Fit train/val past-only
(mean/std features chi fit tren train-window; nested-validation 180d giam sat +
EXPORT val-logits de calibrate-first outlier-robust THAT o audit local sau,
KHONG chon epoch, KHONG tune theo PnL).
Loss DONG BANG configs/opencode_v106_student.json:
  1.0*KL(student||frozen-soft T=1, soft-subset intersect train x soft-universe)
  + 0.2*weighted-ranking(student_logits, hard labels, upweight L-like 2.0x,
        temperature 1.0%, tie-band 0.25%, VERBATIM pairwise + WAIT=0)
  + 3.0*coverage-hinge TREN LOGITS (safety net).
Upweight descriptors EXACT v103 (past-only): vol_high=(atr4/close>=VOL_CUT),
fund_high=(|fund_last|>=1e-4, as-of strict); L-like=(vol_high==0&fund_high==0);
w=2.0 L-like else 1.0; CHI ranking term; KHONG exclude; record weights.
Export logits free units: test predictions_logits + VAL predictions_logits
+ indices + soft_rows + upweight_stats. Portfolio + calibrate-first chay LOCAL sau.
GPU-agnostic guard (hoc tu A2 P100 sm_60): GPU la -> WARN va tiep tuc CPU, KHONG raise.
Bundle FROZEN soft_targets.npz (bytes-identical distill artifact) de train offline.
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

from opencode_r37m_student_features import N_FLAT, build_flat
from opencode_r37m_student_model import (
    COV_FLOOR_POS,
    COV_LAMBDA,
    FUND_ABS,
    KL_WEIGHT,
    RANK_TEMP_PCT,
    RANK_TIE_PCT,
    RANK_WEIGHT,
    TIE_BREAK_EPS,
    UPWEIGHT_LLIKE,
    VOL_CUT_V56,
    StudentSSMTemporal,
    compute_upweights,
    count_params,
    coverage_hinge_logits,
    predict_student_logits,
    student_kl,
    weighted_ranking_loss,
)
from agentic_alpha_lab.models.temporal_validation import nested_split

SOFT_REL = "artifacts/research/opencode_v101_distill/soft_targets.npz"
SOFT_SHA = "ff170795dde5342e5becd401e727daa10c0025a57047c07a9f1217e912556ae1"


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
    return StudentSSMTemporal(candidates, n_flat=N_FLAT, **d)


def load_soft_bundle(root, plan):
    cfg = plan.get("soft_targets_frozen", {})
    rel = cfg.get("file", SOFT_REL)
    exp = cfg.get("bytes_sha256", SOFT_SHA)
    path = root / rel if not str(rel).startswith("/") else Path(rel)
    if not path.is_file():
        alt = root / SOFT_REL
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(f"Thieu frozen soft-targets bundle: {path}")
    if digest(path) != exp:
        raise ValueError("Frozen soft-targets bytes KHONG khop distill artifact (verify sha256)")
    z = np.load(path, allow_pickle=False)
    soft = np.asarray(z["soft_targets"], dtype=np.float32)
    indices = np.asarray(z["indices"], dtype=np.int64)
    fold_of = np.asarray(z["fold_of"], dtype=np.int64)
    if soft.shape != (4076, 16) or indices.shape != (4076,) or not np.isfinite(soft).all():
        raise ValueError("Invalid frozen soft-targets content")
    np.testing.assert_allclose(soft.sum(axis=1), np.ones(len(soft)), rtol=0, atol=1e-5)
    pos_of = {int(ix): int(i) for i, ix in enumerate(indices.tolist())}
    return soft, indices, fold_of, pos_of, str(path)


def upweight_vectors(decisions, fund_path):
    """Descriptors EXACT v103 (past-only): vol_high, fund_high, w (2.0 L-like else 1.0)."""
    atr_ratio = decisions["atr4"].to_numpy(dtype=float) / decisions["close"].to_numpy(dtype=float)
    vol_high = (atr_ratio >= float(VOL_CUT_V56)).astype(np.int64)
    fund = pd.read_parquet(fund_path)
    fund["funding_time"] = pd.to_datetime(fund["funding_time"], utc=True)
    fund = fund.sort_values("funding_time")
    sig = pd.to_datetime(decisions["signal_time"], utc=True)
    left = pd.DataFrame({"signal_time": sig, "_ord": np.arange(len(decisions))}).sort_values("signal_time")
    joined = pd.merge_asof(left, fund[["funding_time", "fundingRate"]],
                           left_on="signal_time", right_on="funding_time",
                           direction="backward", allow_exact_matches=False)
    joined = joined.sort_values("_ord").reset_index(drop=True)
    fund_last = joined["fundingRate"].to_numpy(dtype=float)
    fund_last = np.where(np.isfinite(fund_last), fund_last, 0.0)
    fund_high = (np.abs(fund_last) >= float(FUND_ABS)).astype(np.int64)
    w, like = compute_upweights(vol_high, fund_high, factor=UPWEIGHT_LLIKE)
    return vol_high, fund_high, fund_last, atr_ratio, w, like


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
    soft, soft_indices, soft_fold, soft_pos, soft_path = load_soft_bundle(root, plan)
    vh, fh, fl, atr, w, like = upweight_vectors(decisions, root / plan["funding_source"]["file"])
    return sequence, flat, labels, decisions, candidates, (soft, soft_indices, soft_fold, soft_pos, soft_path), (vh, fh, fl, atr, w, like)


def fold_indices(decisions, parent, plan, fold):
    start, stop = map(pd.Timestamp, parent["folds"][fold])
    train = np.flatnonzero(((decisions.signal_time >= start - pd.Timedelta(days=plan["folds"]["trailing_window_days"])) &
                            (decisions.label_end < start - pd.Timedelta(days=plan["folds"]["embargo_days"]))).to_numpy())
    test = np.flatnonzero(((decisions.signal_time >= start) & (decisions.signal_time < stop) &
                           (decisions.label_end < pd.Timestamp(parent["complete_evaluation_until"]))).to_numpy())
    if len(train) < plan["folds"]["minimum_train_decisions"] or not len(test) or np.intersect1d(train, test).size:
        raise ValueError("Invalid chronological fold")
    return train, test


def loss_params(plan):
    tr = plan.get("training", {})
    if float(tr.get("kl_weight", -1)) != KL_WEIGHT:
        raise ValueError("v106 kl_weight phai 1.0")
    if float(tr.get("ranking_weight_lambda", -1)) != RANK_WEIGHT:
        raise ValueError("v106 ranking_weight_lambda phai 0.2")
    if float(tr.get("upweight_Llike_factor", -1)) != UPWEIGHT_LLIKE:
        raise ValueError("v106 upweight factor phai 2.0")
    if float(tr.get("tie_break_eps", -1)) if "tie_break_eps" in tr else TIE_BREAK_EPS != TIE_BREAK_EPS:
        raise ValueError("v106 tie_break_eps phai 1e-6")
    return (float(tr.get("kl_weight", KL_WEIGHT)),
            float(tr.get("ranking_weight_lambda", RANK_WEIGHT)),
            float(tr.get("coverage_lambda", COV_LAMBDA)),
            float(tr.get("coverage_floor_pos", COV_FLOOR_POS)),
            float(tr.get("ranking_temperature_percent", RANK_TEMP_PCT)),
            float(tr.get("ranking_tie_band_percent", RANK_TIE_PCT)))


def tensors_for(ids, arrays, device):
    sequence, flat, labels = arrays
    return (torch.tensor(sequence[ids], dtype=torch.float32, device=device),
            torch.tensor(flat[ids], dtype=torch.float32, device=device),
            torch.tensor(labels[ids], dtype=torch.float32, device=device))


def run_epoch(model, opt, scaler, arrays, ids, soft_idx_of, soft_mat, w_full, settings, lp, dev, train_mode):
    kl_w, rank_w, lam, flr, rtemp, rtie = lp
    use_amp = bool(settings["amp"]) and dev.type == "cuda" and train_mode
    batch, effective = settings["batch_size"], settings["batch_size"] * settings["accumulation_steps"]
    order = torch.randperm(len(ids), device=ids.device) if train_mode else torch.arange(len(ids), device=ids.device)
    total, kl_acc, rank_acc, cov_acc, pos_acc, count = 0.0, 0.0, 0.0, 0.0, 0.0, 0
    xs_all, xf_all, ys_all = arrays
    w_all = torch.as_tensor(w_full, dtype=torch.float32, device=dev)
    for left in range(0, len(order), effective):
        group = ids[order[left:left + effective]]
        if train_mode:
            opt.zero_grad(set_to_none=True)
        gtotal, gn = 0.0, 0
        for s in range(0, len(group), batch):
            ix = group[s:s + batch]
            with torch.autocast("cuda", enabled=use_amp):
                logits = model(xs_all[ix], xf_all[ix])
            pos = soft_idx_of[ix.cpu().numpy()]
            has = pos >= 0
            if has.any():
                sm = torch.as_tensor(soft_mat[pos[has]], dtype=torch.float32, device=dev)
                kl = student_kl(logits[torch.as_tensor(has, device=dev)], sm)
            else:
                kl = logits.new_zeros(())
            rank, _ = weighted_ranking_loss(logits, ys_all[ix], w_all[ix],
                                            temperature_percent=rtemp, tie_band_percent=rtie)
            cov, mean_pos, _ = coverage_hinge_logits(logits, lam, flr)
            loss = kl_w * kl + rank_w * rank + cov
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite student training loss")
            if train_mode:
                if scaler is not None:
                    scaler.scale(loss * (len(ix) / len(group))).backward()
                else:
                    (loss * (len(ix) / len(group))).backward()
            gtotal += loss.detach().item() * len(ix)
            kl_acc += float(kl.detach()) * len(ix)
            rank_acc += float(rank.detach()) * len(ix)
            cov_acc += float(cov.detach()) * len(ix)
            pos_acc += float(mean_pos) * len(ix)
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
    return total / count, kl_acc / count, rank_acc / count, cov_acc / count, pos_acc / count


def run_fold(plan, parent, inputs, output, seed, fold, dev):
    sequence, flat, labels, decisions, candidates, softb, upb = inputs
    soft_mat, soft_indices, soft_fold, soft_pos, soft_path = softb
    vh, fh, fl, atr, w, like = upb
    settings = plan["training"]
    lp = loss_params(plan)
    train, test = fold_indices(decisions, parent, plan, fold)
    spec = plan["epoch_selection"]
    _, validation, clock = nested_split(decisions, parent["folds"][fold][0],
                                        window_days=spec["window_days"],
                                        validation_days=spec["validation_days"],
                                        embargo_days=spec["embargo_days"],
                                        minimum_train=spec["minimum_train"],
                                        minimum_validation=spec["minimum_validation"])
    n = len(decisions)
    soft_idx_of = np.full(n, -1, dtype=np.int64)
    for ix, p in soft_pos.items():
        soft_idx_of[int(ix)] = int(p)
    tr_soft = soft_idx_of[train] >= 0
    va_soft = soft_idx_of[validation] >= 0
    w_train = w[train]
    up_stats = {"n_train": int(len(train)), "n_train_soft": int(tr_soft.sum()),
                "n_Llike_train": int(like[train].sum()),
                "frac_Llike_train": float(like[train].mean()),
                "mean_w_Llike_train": float(w_train[like[train]].mean()) if like[train].any() else None,
                "mean_w_rest_train": float(w_train[~like[train]].mean()) if (~like[train]).any() else None,
                "n_validation": int(len(validation)), "n_val_soft": int(va_soft.sum()),
                "n_test": int(len(test))}
    target = output / f"seed{seed}/checkpoints/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    if not isinstance(model, StudentSSMTemporal):
        raise ValueError("v106 model phai la StudentSSMTemporal (logits free units)")
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.to(dev)
    full = tensors_for(np.arange(n), (sequence, flat, labels), dev)
    tid = torch.tensor(train, dtype=torch.int64, device=dev)
    vid = torch.tensor(validation, dtype=torch.int64, device=dev)
    opt = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"],
                            weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=bool(settings["amp"]) and dev.type == "cuda")
    if dev.type == "cpu":
        scaler = None
    history, kl_hist, rank_hist, cov_hist, pos_hist, val_hist = [], [], [], [], [], []
    epochs = 16
    assert int(settings.get("epochs", 16)) == 16, f"v106 FIXED 16 epochs, nhan {epochs}"
    for epoch in range(epochs):
        model.train()
        tl, tkl, tr_, tc, tp = run_epoch(model, opt, scaler, full, tid, soft_idx_of, soft_mat, w, settings, lp, dev, True)
        model.eval()
        with torch.no_grad():
            vl, vkl, vr, vc, vp = run_epoch(model, None, None, full, vid, soft_idx_of, soft_mat, w, settings, lp, dev, False)
        history.append(tl)
        kl_hist.append(tkl)
        rank_hist.append(tr_)
        cov_hist.append(tc)
        pos_hist.append(tp)
        val_hist.append(vl)
        write_json(target / "progress.json", {"seed": seed, "fold": fold, "epoch": epoch + 1,
                                              "loss": tl, "kl": tkl, "rank": tr_, "cov": tc,
                                              "mean_pos": tp, "val_loss": vl, "val_kl": vkl})
        print(json.dumps({"seed": seed, "fold": fold, "epoch": epoch + 1, "loss": tl,
                          "kl": tkl, "rank": tr_, "cov": tc, "mean_pos": tp, "val_loss": vl}), flush=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(target / "model.safetensors"))
    np.savez_compressed(target / "indices.npz", train=train, validation=validation, test=test)
    write_json(target / "soft_rows.json", {"n_train_soft": up_stats["n_train_soft"],
                                           "n_val_soft": up_stats["n_val_soft"],
                                           "soft_bundle": soft_path,
                                           "kl_empty_fallback": bool(up_stats["n_train_soft"] == 0)})
    write_json(target / "upweight_stats.json", up_stats)
    details = {"seed": seed, "fold": fold, "training": settings,
               "loss": {"kl_weight": lp[0], "ranking_weight": lp[1],
                        "ranking_temperature_percent": lp[4],
                        "ranking_tie_band_percent": lp[5],
                        "coverage": {"lambda": lp[2], "floor_pos": lp[3], "domain": "STUDENT-LOGIT free units"},
                        "upweight": {"rule": "L-like=(vol_high==0)&(fund_high==0), factor 2.0, ranking-only, no-exclude",
                                     "vol_cut_v56": VOL_CUT_V56, "fund_abs": FUND_ABS, **up_stats}},
               "epoch_mode": "FIXED 16 (no early-stop; validation monitor-only past-only + export)",
               "validation_clock": clock, "val_loss_by_epoch": val_hist,
               "kl_by_epoch": kl_hist, "rank_by_epoch": rank_hist,
               "parameters": count_params(model), "training_loss": history,
               "train_decisions": len(train), "validation_decisions": len(validation),
               "test_decisions": len(test),
               "last_training_label_end": str(decisions.iloc[train].label_end.max()),
               "model_family": "distill_student_ssm_v106", "torch": torch.__version__,
               "numpy": np.__version__, "pandas": pd.__version__,
               "python": platform.python_version(), "device": str(dev),
               "weights_sha256": digest(target / "model.safetensors"),
               "local_replay_required": True, "live_approved": False}
    write_json(target / "metadata.json", details)
    forecast = predict_student_logits(model, sequence[test], flat[test], batch_size=32)
    val_forecast = predict_student_logits(model, sequence[validation], flat[validation], batch_size=32)
    restored = make_model(plan, candidates).to(dev)
    restored.load_state_dict(load_file(str(target / "model.safetensors")))
    replay = predict_student_logits(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.savez_compressed(target / "replay.npz", sequences=sequence[test][:8],
                        features=flat[test][:8], predictions=forecast[:8])
    pred_dir = output / f"seed{seed}/temporal_neural/fold_{fold}"
    pred_dir.mkdir(parents=True)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite test logits")
    if not np.isfinite(val_forecast).all():
        raise ValueError("Nonfinite validation logits")
    if forecast.shape != (len(test), 16) or val_forecast.shape != (len(validation), 16):
        raise ValueError("Invalid student logit shapes")
    np.save(pred_dir / "predictions_logits.npy", forecast.astype(np.float32))
    np.save(pred_dir / "val_predictions_logits.npy", val_forecast.astype(np.float32))
    details.update(state="complete" if parity else "parity_failed", gpu_reload_parity=parity,
                   gpu_reload_max_error=float(np.max(np.abs(replay - forecast[:8]))),
                   prediction_sha256=digest(pred_dir / "predictions_logits.npy"),
                   val_prediction_sha256=digest(pred_dir / "val_predictions_logits.npy"),
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
    if plan.get("model_family") != "distill_student_ssm_v106":
        raise ValueError("Unknown plan family for v106 driver")
    tr = plan.get("training", {})
    assert int(tr.get("epochs", 0)) == 16, "v106 FIXED 16 epochs"
    assert float(tr.get("ranking_weight_lambda", -1)) == 0.2, "ranking_weight_lambda phai 0.2"
    assert float(tr.get("kl_weight", -1)) == 1.0, "kl_weight phai 1.0"
    assert float(tr.get("upweight_Llike_factor", -1)) == 2.0, "upweight factor phai 2.0"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v106 bo early-stop"
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
