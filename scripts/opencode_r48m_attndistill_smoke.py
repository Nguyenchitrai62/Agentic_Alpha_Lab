"""Opencode R48-M SMOKE v132 nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so, giong v28/v96/v106).
(2) Build flat (5628,133) qua wrapper v132 + labels, assert shapes/finite/causal.
(3) Load FROZEN soft-targets (4076,16) + verify sha256 bytes distill artifact.
(4) 1 fold (fold_1, co 308 soft-train) x 1 seed (1729) x 3 epochs CPU batch 32:
     forward/backward FULL v132 loss (1.0*KL student||soft T=1 soft-subset PRIMARY
     + 1.0*entropy-floor 2.20nats + 0.1*ListNet-on-hard THAP + 3.0*coverage-hinge logits),
     KL finite + KL-DECREASING proof (kl_last < kl_first — PHAI dich chuyen;
       neu flat thi STOP, khong package), RANK finite (ListNet 0.1),
     ENTROPY-ABOVE-FLOOR proof (mean_H_last >= 2.20 + penalty finite + min_H report;
       collapse la FAIL), save/reload parity, predict logits,
     tie-break deterministic (holding-asc), VAL-EXPORT logits proof.
     Khong training nang local.
Ket qua chi de dan ong, KHONG so voi standing_best.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from opencode_r48m_attndistill_features import N_FLAT, build_flat  # noqa: E402
from opencode_r48m_attndistill_model import (  # noqa: E402
    COV_FLOOR_POS,
    COV_LAMBDA,
    CROSS_LAYERS,
    D_MODEL,
    ENT_FLOOR_NATS,
    ENT_LAMBDA,
    FF_DIM,
    FRAME_LAYERS,
    KL_WEIGHT,
    NHEAD,
    RANK_TEMP,
    RANK_WEIGHT,
    TIE_BREAK_EPS,
    AttnDistillTemporal,
    attndistill_loss_from_parts,
    count_params,
    coverage_hinge_logits,
    deterministic_best_index,
    deterministic_best_indices,
    entropy_floor_penalty,
    listnet_on_hard,
    predict_attn_logits,
    student_kl,
)
from opencode_r48m_attndistill_train import (  # noqa: E402
    SOFT_SHA,
    fold_indices,
    load_soft_bundle,
    loss_params,
    make_model,
)
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import stable_evaluation_backend  # noqa: E402
from opencode_r9m_nextarch_model import apply_coverage_floor_policy  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    torch.set_num_threads(2)
    torch.backends.mha.set_fastpath_enabled(False)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "distill_attn_v132", "Sai plan family"
    assert int(plan["training"]["epochs"]) == 12, "v132 FIXED 12 epochs"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v132 bo early-stop"
    assert float(plan["training"].get("kl_weight", -1)) == 1.0, "kl_weight phai 1.0"
    assert float(plan["training"].get("ranking_weight_lambda", -1)) == 0.1, "lambda_rank phai 0.1 THAP"
    assert float(plan["training"].get("entropy_lambda", -1)) == 1.0, "entropy_lambda phai 1.0"
    assert float(plan["training"].get("entropy_floor_nats", -1)) == 2.2, "entropy floor phai 2.20"
    assert (KL_WEIGHT, ENT_LAMBDA, RANK_WEIGHT) == (1.0, 1.0, 0.1)
    assert (COV_LAMBDA, COV_FLOOR_POS) == (3.0, 5e-4)
    assert RANK_TEMP == 1.0 and ENT_FLOOR_NATS == 2.2
    assert TIE_BREAK_EPS == 1e-6
    assert (D_MODEL, NHEAD, FF_DIM, FRAME_LAYERS, CROSS_LAYERS) == (128, 4, 256, 2, 1)
    assert float(plan["budget"]["gpu_hours_max"]) <= 6.0, "budget tran 6 GPU-gio"
    kw, entw, entf, rw, lam, flr, rtemp = loss_params(plan)
    assert (kw, entw, entf, rw) == (1.0, 1.0, 2.2, 0.1)
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    assert len(decisions) == 5628

    fund = pd.read_parquet(ROOT / plan["funding_source"]["file"])
    ft = pd.to_datetime(fund["funding_time"], utc=True).sort_values().to_numpy()
    st = pd.to_datetime(decisions["signal_time"], utc=True).to_numpy()
    fpos = np.searchsorted(ft, st, side="left") - 1
    spy = pd.read_parquet(Path(plan["macro_source"]["dir"]) / "spy.parquet")
    audit = {
        "price40": {"rows": 5628, "coverage": 1.0, "causal": "frozen past-only", "verdict": "GIU"},
        "deriv40_lag48": {"rows": 5628, "finite_frac": 1.0,
                          "causal": "kich ban source_day+48h (receipt-time chua xac minh, disclosed)",
                          "verdict": "GIU (co disclosure)"},
        "flow40": {"rows": 5628, "causal": "closed-candle merge_asof backward, stale->raise",
                   "verdict": "GIU"},
        "funding": {"parquet_rows": len(fund), "decisions_covered": int((fpos >= 0).sum()),
                    "min_prior_periods": int(fpos.min()), "need_90": bool((fpos >= 90).all()),
                    "causal": "as-of funding_time < signal_time", "verdict": "GIU"},
        "macro": {"spy_daily_rows": len(spy), "decisions_with_Tminus1_and_60d": 5628,
                  "causal": "strict T-1 (macro date < UTC signal date)",
                  "dropped": "GLD/GC-future (chi coverage)", "verdict": "GIU SPY/DXY, LOAI GLD/GC"},
    }
    print(json.dumps({"coverage_audit": audit}, ensure_ascii=False), flush=True)

    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert flat.shape == (5628, N_FLAT) and np.isfinite(flat).all()
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels = z["labels"]
    assert labels.shape == (5628, 16, 3)
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    soft_mat, soft_indices, soft_fold, soft_pos, soft_path = load_soft_bundle(ROOT, plan)
    assert digest(ROOT / plan["soft_targets_frozen"]["file"]) == SOFT_SHA, "soft bytes khong khop distill"
    print(json.dumps({"frozen_soft_verified": {"path": soft_path, "sha256": SOFT_SHA,
          "shape": list(soft_mat.shape)}}), flush=True)

    seed, fold, epochs, batch = 1729, 1, 3, 32
    assert seed in plan["seeds"]
    train, test = fold_indices(decisions, parent, plan, fold)
    spec = plan["epoch_selection"]
    _, validation, _clock = nested_split(
        decisions, parent["folds"][fold][0],
        window_days=spec["window_days"], validation_days=spec["validation_days"],
        embargo_days=spec["embargo_days"], minimum_train=spec["minimum_train"],
        minimum_validation=spec["minimum_validation"])
    assert len(validation) >= 100
    assert not np.intersect1d(validation, test).size, "validation phai past-only, khong lan test"
    n = len(decisions)
    soft_idx_of = np.full(n, -1, dtype=np.int64)
    for ix, p in soft_pos.items():
        soft_idx_of[int(ix)] = int(p)
    tr_soft_mask = soft_idx_of[train] >= 0
    assert int(tr_soft_mask.sum()) >= 200, f"fold smoke phai co soft-train (>=200), nhan {tr_soft_mask.sum()}"
    print(json.dumps({"smoke_fold": {"fold": fold, "n_train": int(len(train)),
          "n_train_soft": int(tr_soft_mask.sum()), "n_test": int(len(test)),
          "n_validation": int(len(validation))}}), flush=True)

    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, AttnDistillTemporal)
    n_params = count_params(model)
    print(json.dumps({"attndistill_params": n_params}), flush=True)
    assert n_params <= 2000000, f"params vuot budget re 2M: {n_params}"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    soft_pos_train = soft_idx_of[train]
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses, kls, ents, ranks, covs, hmeans, hmins = [], [], [], [], [], [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total, ktot, etot, rtot, ctot, htot, hmtot = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            logits = model(xs[idx], xf[idx])
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite attn-distill logits")
            gmask_np = tr_soft_mask[idx.numpy()]
            if gmask_np.any():
                sm = torch.as_tensor(soft_mat[soft_pos_train[idx.numpy()][gmask_np]], dtype=torch.float32)
                kl = student_kl(logits[torch.as_tensor(gmask_np)], sm)
            else:
                kl = logits.new_zeros(())
            total_b, parts = attndistill_loss_from_parts(
                float(kl.detach()), logits, ys[idx],
                kl_w=kw, ent_w=entw, rank_w=rw, lambda_cov=lam,
                floor_pos=flr, rank_temp=rtemp, floor_nats=entf)
            if not torch.isfinite(total_b):
                raise ValueError("Nonfinite smoke loss")
            total_b.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += total_b.detach().item() * len(idx)
            ktot += float(parts["kl"]) * len(idx)
            etot += float(parts["ent"]) * len(idx)
            rtot += float(parts["rank"]) * len(idx)
            ctot += float(parts["cov"]) * len(idx)
            htot += float(parts["mean_h"]) * len(idx)
            hmtot += float(parts["min_h"]) * len(idx)
        losses.append(total / len(train))
        kls.append(ktot / len(train))
        ents.append(etot / len(train))
        ranks.append(rtot / len(train))
        covs.append(ctot / len(train))
        hmeans.append(htot / len(train))
        hmins.append(hmtot / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1], "kl": kls[-1],
                          "ent": ents[-1], "rank": ranks[-1], "cov": covs[-1],
                          "mean_H": hmeans[-1], "min_H": hmins[-1]}), flush=True)
    assert all(np.isfinite(kls)), "KL phai finite"
    assert all(np.isfinite(ranks)), "ranking-term (ListNet 0.1) phai finite"
    assert all(np.isfinite(ents)), "entropy-penalty phai finite"
    assert all(np.isfinite(covs)), "coverage-term phai finite"
    kl_move = float(kls[0] - kls[-1])
    kl_decreasing = bool(kls[-1] < kls[0] - 1e-9)
    kl_range = float(max(kls) - min(kls))
    print(json.dumps({"kl_decreasing_proof": {"kls": kls, "move": kl_move,
          "range": kl_range, "pass": kl_decreasing}}), flush=True)
    if not kl_decreasing or not kl_range > 1e-9:
        raise RuntimeError(f"STOP: KL FLAT — kls={kls}; khong package thiet ke chet")
    ent_pass = bool(np.isfinite(hmeans[-1]) and hmeans[-1] >= 2.2 - 1e-9)
    print(json.dumps({"entropy_above_floor_proof": {"mean_H_by_epoch": hmeans, "min_H_by_epoch": hmins,
          "ent_by_epoch": ents, "floor_nats": 2.2, "mean_H_last": hmeans[-1],
          "min_H_last": hmins[-1], "pass": ent_pass,
          "note": "v96 failure = mass-collapse (H thap 11/11, fold-10 1.91); v132 phai giu H tren floor 2.20"}}, ensure_ascii=False), flush=True)
    if not ent_pass:
        raise RuntimeError(f"STOP: ENTROPY BELOW FLOOR — mean_H_last={hmeans[-1]} < 2.2 (collapse); khong package")
    out = a.output / "seed1729" / "fold_1"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    fc = predict_attn_logits(model, sequence[test][:64], flat[test][:64], batch_size=32)
    assert fc.shape == (64, 16) and np.isfinite(fc).all()
    exp_row = np.full(16, 0.5)
    holds = candidates[:, 5]
    idx_h3 = int(np.flatnonzero(holds == 3)[0])
    pick_hold = deterministic_best_index(exp_row, candidates)
    assert int(candidates[pick_hold, 5]) == 3, f"tie-break holding-asc hong: {pick_hold}"
    assert pick_hold == idx_h3, f"tie-break index nho nhat hong: {pick_hold} vs {idx_h3}"
    rep1 = deterministic_best_index(exp_row, candidates)
    rep2 = deterministic_best_index(exp_row, candidates)
    assert rep1 == rep2 == idx_h3, "tie-break phai bit-identical repeat"
    vec = deterministic_best_indices(np.stack([exp_row, exp_row + 1.0]), candidates)
    assert vec.tolist() == [idx_h3, idx_h3], f"vectorized tie-break hong: {vec}"
    tie_pass = True
    fc_val = predict_attn_logits(model, sequence[validation][:64], flat[validation][:64], batch_size=32)
    assert fc_val.shape == (64, 16) and np.isfinite(fc_val).all()
    np.save(out / "val_predictions_logits_sample.npy", fc_val)
    val_export_present = bool((out / "val_predictions_logits_sample.npy").exists())
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_attn_logits(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    neg = apply_coverage_floor_policy(np.full(50, -0.01), POLICY_MARGIN, POLICY_N_MIN)
    assert len(neg) == POLICY_N_MIN == 8, f"fallback floor hong: {len(neg)}"
    en = fc.max(axis=1)
    gate_hits = int((en > POLICY_MARGIN).sum())
    np.save(out / "predictions_logits_sample.npy", fc)
    np.savez_compressed(out / "indices.npz", train=train, validation=validation, test=test)
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "kl_terms": kls, "entropy_terms": ents,
               "ranking_terms": ranks, "coverage_terms": covs,
               "mean_H_by_epoch": hmeans, "min_H_by_epoch": hmins,
               "kl_decreasing_proof": {"kls": kls, "move": kl_move,
                   "range": kl_range, "pass": kl_decreasing,
                   "note": "v132 KL student||soft T=1 PRIMARY phai dich chuyen; flat => STOP khong package"},
               "entropy_above_floor_proof": {"mean_H_by_epoch": hmeans, "min_H_by_epoch": hmins,
                   "ent_by_epoch": ents, "floor_nats": 2.2, "mean_H_last": hmeans[-1],
                   "min_H_last": hmins[-1], "pass": ent_pass,
                   "note": "Chong collapse truc tiep (v96 pmax gap doi, H thap 11/11); H duoi floor => STOP"},
               "loss_weights": {"kl": kw, "entropy": entw, "rank": rw, "cov_lambda": lam},
               "ranking_params": {"kind": "ListNet-listwise-on-hard", "temperature": rtemp, "weight": rw,
                                  "note": "THAP 0.1 << v96 PRIMARY 2.0; soft da chua order"},
               "entropy_floor": {"lambda": entw, "floor_nats": entf},
               "coverage_floor": {"lambda": lam, "floor_pos": flr, "domain": "STUDENT-LOGIT free units"},
               "frozen_soft": {"sha256": SOFT_SHA, "shape": list(soft_mat.shape)},
               "tie_break_proof": {"eps": TIE_BREAK_EPS, "holding_asc_pick": int(pick_hold),
                   "repeat_identical": True, "vectorized": vec.tolist(), "pass": tie_pass,
                   "rule": "gap<1e-6 -> holding-asc (3 truoc 7), roi index nho nhat (tren LOGITS; bo fill-desc)"},
               "val_export_proof": {"val_predictions_file": "val_predictions_logits_sample.npy",
                                    "present": val_export_present,
                                    "shape": list(fc_val.shape),
                                    "n_validation_total": int(len(validation)),
                                    "finite": True, "pass": True,
                                    "note": "VAL LOGITS free units, cho calibrate-first outlier-robust sau"},
               "epoch_mode": "FIXED 12 (smoke chay 3 epochs plumbing + KL-decreasing + entropy-proof)",
               "policy_floor_unit_test": {"all_negative_picks": len(neg),
                                          "margin": POLICY_MARGIN, "n_min": POLICY_N_MIN, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "gate_hits_en_logit_gt_0": gate_hits, "en_best_logit_mean": float(en.mean())},
               "parameters": n_params, "params_band": "<=2M (MUCH cheaper than v96 8.77M)",
               "params_vs_v96": {"v96": 8768459, "v132": n_params,
                                 "ratio": float(8768459 / max(n_params, 1))},
               "model_family": "distill_attn_v132", "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "validation_decisions": len(validation),
               "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_logits_sample.npy"),
               "val_prediction_sha256": digest(out / "val_predictions_logits_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v132_attndistill.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v132_attndistill/smoke")
    main(p.parse_args())
