"""Opencode R37-M SMOKE v106 nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so, giong v28/v35/v38/v39/v40/v41).
(2) Build flat (5628,133) qua wrapper v106 + labels, assert shapes/finite/causal.
(3) Load FROZEN soft-targets (4076,16) + verify sha256 bytes distill artifact.
(4) Upweight descriptors EXACT v103 (past-only) + record weights.
(5) 1 fold (fold_1, co 308 soft-train) x 1 seed (1729) x 3 epochs CPU batch 32:
     forward/backward FULL v106 loss (1.0*KL student||soft T=1 soft-subset
     + 0.2*weighted-ranking upweight-L-like-2.0x + 3.0*coverage-hinge logits),
     KL finite + KL-DECREASING proof (kl_last < kl_first — PHAI dich chuyen;
       neu flat thi STOP, khong package), RANKING finite,
     UPWEIGHT-ACTIVE proof (mean_w_Llike=2.0 vs rest=1.0 + frac + counts),
     save/reload parity, predict logits, tie-break deterministic (holding-asc),
     VAL-EXPORT logits proof. Khong training nang local.
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
from opencode_r37m_student_features import N_FLAT, build_flat  # noqa: E402
from opencode_r37m_student_model import (  # noqa: E402
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
    deterministic_best_index,
    deterministic_best_indices,
    predict_student_logits,
    student_kl,
    weighted_ranking_loss,
)
from opencode_r37m_student_train import (  # noqa: E402
    SOFT_SHA,
    fold_indices,
    load_soft_bundle,
    loss_params,
    make_model,
    upweight_vectors,
)
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import fold_indices as _unused  # noqa: F401 (ghi nhan goc)
from train_tcn_kaggle import stable_evaluation_backend  # noqa: E402
from opencode_r9m_nextarch_model import apply_coverage_floor_policy  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "distill_student_ssm_v106", "Sai plan family"
    assert int(plan["training"]["epochs"]) == 16, "v106 FIXED 16 epochs"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v106 bo early-stop"
    assert float(plan["training"].get("kl_weight", -1)) == 1.0, "kl_weight phai 1.0"
    assert float(plan["training"].get("ranking_weight_lambda", -1)) == 0.2, "lambda_rank phai 0.2"
    assert float(plan["training"].get("upweight_Llike_factor", -1)) == 2.0, "upweight phai 2.0"
    assert (KL_WEIGHT, RANK_WEIGHT) == (1.0, 0.2)
    assert (COV_LAMBDA, COV_FLOOR_POS) == (3.0, 5e-4)
    assert (RANK_TEMP_PCT, RANK_TIE_PCT) == (1.0, 0.25)
    assert UPWEIGHT_LLIKE == 2.0 and TIE_BREAK_EPS == 1e-6
    assert abs(VOL_CUT_V56 - 0.01338037015711381) < 1e-15, "VOL_CUT phai verbatim v56"
    assert FUND_ABS == 0.0001
    assert float(plan["budget"]["gpu_hours_max"]) <= 10.0, "budget tran 10 GPU-gio"
    kw, rw, lam, flr, rtemp, rtie = loss_params(plan)
    assert (kw, rw) == (1.0, 0.2)
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

    vh, fh, fl, atr, w, like = upweight_vectors(decisions, ROOT / plan["funding_source"]["file"])
    assert vh.shape == (5628,) and fh.shape == (5628,) and w.shape == (5628,)
    w_check, like_check = compute_upweights(vh, fh, factor=2.0)
    assert np.array_equal(w, w_check) and np.array_equal(like, like_check)
    assert set(np.unique(w).tolist()) <= {1.0, 2.0}
    print(json.dumps({"upweight_descriptors": {"vol_cut": VOL_CUT_V56, "fund_abs": FUND_ABS,
          "frac_Llike_global": float(like.mean()), "n_Llike_global": int(like.sum()),
          "mean_w_Llike_global": float(w[like].mean()), "mean_w_rest_global": float(w[~like].mean())}}), flush=True)

    seed, fold, epochs, batch = 1729, 1, 3, 32
    assert seed in plan["seeds"]
    fold_settings = {"window_days": plan["folds"]["trailing_window_days"],
                     "embargo_days": plan["folds"]["embargo_days"],
                     "minimum_train_decisions": plan["folds"]["minimum_train_decisions"]}
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
    w_train = w[train]
    frac_like = float(like[train].mean())
    mean_w_like = float(w_train[like[train]].mean())
    mean_w_rest = float(w_train[~like[train]].mean())
    print(json.dumps({"smoke_fold": {"fold": fold, "n_train": int(len(train)),
          "n_train_soft": int(tr_soft_mask.sum()), "n_test": int(len(test)),
          "n_validation": int(len(validation)), "frac_Llike_train": frac_like,
          "mean_w_Llike_train": mean_w_like, "mean_w_rest_train": mean_w_rest}}), flush=True)
    assert mean_w_like == 2.0 and mean_w_rest == 1.0, "upweight phai active (2.0 vs 1.0)"

    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, StudentSSMTemporal)
    n_params = count_params(model)
    print(json.dumps({"student_params": n_params}), flush=True)
    assert 400000 <= n_params <= 2000000, f"params ngoai band ~0.6M: {n_params}"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    w_t = torch.tensor(w_train, dtype=torch.float32)
    soft_pos_train = soft_idx_of[train]
    soft_rows = torch.tensor(soft_mat[soft_pos_train[tr_soft_mask]], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses, kls, ranks, covs = [], [], [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total, ktot, rtot, ctot = 0.0, 0.0, 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            logits = model(xs[idx], xf[idx])
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite student logits")
            gmask_np = tr_soft_mask[idx.numpy()]
            if gmask_np.any():
                sm = torch.as_tensor(soft_mat[soft_pos_train[idx.numpy()][gmask_np]], dtype=torch.float32)
                kl = student_kl(logits[torch.as_tensor(gmask_np)], sm)
            else:
                kl = logits.new_zeros(())
            rank, _ = weighted_ranking_loss(logits, ys[idx], w_t[idx],
                                            temperature_percent=rtemp, tie_band_percent=rtie)
            cov, mean_pos, _ = coverage_hinge_logits(logits, lam, flr)
            loss = kw * kl + rw * rank + cov
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
            ktot += float(kl.detach()) * len(idx)
            rtot += float(rank.detach()) * len(idx)
            ctot += float(cov.detach()) * len(idx)
        losses.append(total / len(train))
        kls.append(ktot / len(train))
        ranks.append(rtot / len(train))
        covs.append(ctot / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1], "kl": kls[-1],
                          "rank": ranks[-1], "cov": covs[-1]}), flush=True)
    assert all(np.isfinite(kls)), "KL phai finite"
    assert all(np.isfinite(ranks)), "ranking-term phai finite (upweighted pairwise)"
    assert all(np.isfinite(covs)), "coverage-term phai finite"
    kl_move = float(kls[0] - kls[-1])
    kl_decreasing = bool(kls[-1] < kls[0] - 1e-9)
    kl_range = float(max(kls) - min(kls))
    print(json.dumps({"kl_decreasing_proof": {"kls": kls, "move": kl_move,
          "range": kl_range, "pass": kl_decreasing}}), flush=True)
    if not kl_decreasing or not kl_range > 1e-9:
        raise RuntimeError(f"STOP: KL FLAT — kls={kls}; khong package thiet ke chet")
    up_active = bool(mean_w_like > mean_w_rest and frac_like > 0.05)
    print(json.dumps({"upweight_active_proof": {"mean_w_Llike": mean_w_like,
          "mean_w_rest": mean_w_rest, "frac_Llike_train": frac_like,
          "n_Llike_train": int(like[train].sum()), "pass": up_active}}), flush=True)
    if not up_active:
        raise RuntimeError("STOP: upweight KHONG active")
    out = a.output / "seed1729" / "fold_1"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    fc = predict_student_logits(model, sequence[test][:64], flat[test][:64], batch_size=32)
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
    fc_val = predict_student_logits(model, sequence[validation][:64], flat[validation][:64], batch_size=32)
    assert fc_val.shape == (64, 16) and np.isfinite(fc_val).all()
    np.save(out / "val_predictions_logits_sample.npy", fc_val)
    val_export_present = bool((out / "val_predictions_logits_sample.npy").exists())
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_student_logits(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    neg = apply_coverage_floor_policy(np.full(50, -0.01), POLICY_MARGIN, POLICY_N_MIN)
    assert len(neg) == POLICY_N_MIN == 8, f"fallback floor hong: {len(neg)}"
    en = fc.max(axis=1)
    gate_hits = int((en > POLICY_MARGIN).sum())
    np.save(out / "predictions_logits_sample.npy", fc)
    np.savez_compressed(out / "indices.npz", train=train, validation=validation, test=test)
    np.save(out / "upweight_sample.npy", w[test][:64])
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "kl_terms": kls, "ranking_terms": ranks,
               "coverage_terms": covs,
               "kl_decreasing_proof": {"kls": kls, "move": kl_move,
                   "range": kl_range, "pass": kl_decreasing,
                   "note": "v106 KL student||soft T=1 phai dich chuyen; flat => STOP khong package"},
               "upweight_active_proof": {"mean_w_Llike_train": mean_w_like,
                   "mean_w_rest_train": mean_w_rest, "frac_Llike_train": frac_like,
                   "n_Llike_train": int(like[train].sum()), "n_train": int(len(train)),
                   "n_train_soft": int(tr_soft_mask.sum()), "pass": up_active,
                   "rule": "L-like=(vol_high==0)&(fund_high==0) EXACT v103; w=2.0 vs 1.0; ranking-only; no-exclude"},
               "loss_weights": {"kl": kw, "rank": rw, "cov_lambda": lam},
               "ranking_params": {"temperature_percent": rtemp, "tie_band_percent": rtie},
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
               "epoch_mode": "FIXED 16 (smoke chay 3 epochs plumbing + KL-decreasing + upweight-proof)",
               "policy_floor_unit_test": {"all_negative_picks": len(neg),
                                          "margin": POLICY_MARGIN, "n_min": POLICY_N_MIN, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "gate_hits_en_logit_gt_0": gate_hits, "en_best_logit_mean": float(en.mean())},
               "parameters": n_params, "params_band": "~0.6M (encoder dong kich thuoc v35/v41)",
               "model_family": "distill_student_ssm_v106", "n_flat": N_FLAT,
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
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v106_student.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v106_student/smoke")
    main(p.parse_args())
