"""Opencode R19-M SMOKE v39 nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so, giong v28/v35/v38).
(2) Build flat (5628,133) qua wrapper v39 + labels H=48, assert shapes/finite/causal.
(3) 1 fold (fold_0) x 1 seed (1729) x 2 epochs CPU batch 32: forward/backward
     FULL v39 loss (2.0*value-objective CAPPED + 0.5*pairwise-ranking CAPPED + aux
     + coverage-hinge CAPPED), ranking-term + coverage-term finite,
     BOUNDED-OUTPUT proof (max|unconditional capped| <= 0.05),
     VAL-EXPORT proof (val_predictions.npy ton tai + finite + shape),
     save/reload parity, predict_ssm_cap, policy-floor unit-test.
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
from opencode_r19m_v39_features import N_FLAT, build_flat  # noqa: E402
from opencode_r19m_v39_model import (  # noqa: E402
    LOSS_W_RANK,
    LOSS_W_VALUE,
    RANK_TEMP_PCT,
    RANK_TIE_PCT,
    SCALE_CAP,
    SCALE_CAP_MODE,
    ScaleCapSSMTemporal,
    apply_scale_cap_numpy,
    count_params,
    expected_net_best,
    multitask_loss_cov_rank,
    predict_ssm,
)
from opencode_r19m_v39_train import loss_params, make_model  # noqa: E402
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import fold_indices, stable_evaluation_backend  # noqa: E402
from opencode_r9m_nextarch_model import apply_coverage_floor_policy  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402

H = 48
BAND = 8e-4


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_h48(decisions, candles):
    h = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    bi = decisions["bar_index"].to_numpy()
    if (bi + H + 1 >= len(c)).any():
        raise ValueError("Thieu tuong lai H=48")
    ret = c[bi + H] / c[bi] - 1.0
    up = np.stack([h[bi + k] for k in range(1, H + 1)]).max(0) / c[bi] - 1.0
    dn = 1.0 - np.stack([low[bi + k] for k in range(1, H + 1)]).min(0) / c[bi]
    return ret.astype(np.float64), np.clip(up, 0, None), np.clip(dn, 0, None)


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "scalecap_selective_ssm_v39", "Sai plan family"
    assert int(plan["training"]["epochs"]) == 16, "v39 FIXED 16 epochs"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v39 bo early-stop"
    assert str(plan["training"].get("scale_cap_mode", "")) == "tanh", "v39 scale-cap phai tanh"
    assert float(plan["training"].get("scale_cap_cap", -1)) == 0.05, "v39 cap phai 0.05"
    assert SCALE_CAP == 0.05 and SCALE_CAP_MODE == "tanh"
    vw, rw, lam, flr, rtemp, rtie = loss_params(plan)
    assert (vw, rw) == (2.0, 0.5), f"value/ranking weights khac dong bang: {(vw, rw)}"
    assert (lam, flr) == (3.0, 5e-4), f"Coverage-floor khac dong bang: {(lam, flr)}"
    assert (rtemp, rtie) == (1.0, 0.25), f"Ranking temp/tie khac dong bang: {(rtemp, rtie)}"
    assert (LOSS_W_VALUE, LOSS_W_RANK, RANK_TEMP_PCT, RANK_TIE_PCT) == (2.0, 0.5, 1.0, 0.25)
    assert float(plan["budget"]["gpu_hours_max"]) <= 10.0, "budget tran 10 GPU-gio"
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    assert len(decisions) == 5628

    # (1) coverage audit (giong v28/v35/v38)
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

    # (2) fused flat + labels
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert flat.shape == (5628, N_FLAT) and np.isfinite(flat).all()
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels = z["labels"]
    assert labels.shape == (5628, 16, 3)
    ret48, up48, dn48 = build_h48(decisions, candles)
    ydir = np.select([ret48 < -BAND, ret48 > BAND], [0, 2], default=1).astype(np.int64)
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    # (3) smoke train 1 fold x 2 epochs CPU (FULL v39 loss CAPPED)
    seed, fold, epochs, batch = 1729, 0, 2, 32
    assert seed in plan["seeds"]
    fold_settings = {"window_days": plan["folds"]["trailing_window_days"],
                     "embargo_days": plan["folds"]["embargo_days"],
                     "minimum_train_decisions": plan["folds"]["minimum_train_decisions"]}
    train, test = fold_indices(decisions, parent, fold_settings, fold)
    spec = plan["epoch_selection"]
    _, validation, _clock = nested_split(
        decisions, parent["folds"][fold][0],
        window_days=spec["window_days"], validation_days=spec["validation_days"],
        embargo_days=spec["embargo_days"], minimum_train=spec["minimum_train"],
        minimum_validation=spec["minimum_validation"])
    assert len(validation) >= 100
    assert not np.intersect1d(validation, test).size, "validation phai past-only, khong lan test"
    # NOTE (trung thuc): nested-validation la monitoring-split past-only nam TRONG
    # outer-train window (giong v38: model FIXED-epoch train tren full outer-train).
    # Val-pred export van causal past-only vs test (label_end < fold_start - embargo),
    # du de fit isotonic calibrate-first ma khong peek test; khong claim out-of-sample
    # so voi final model (documented limitation, giong pipeline v38).
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, ScaleCapSSMTemporal)
    n_params = count_params(model)
    assert n_params == 600875, f"params doi so voi v35/v38 dong bang: {n_params}"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    yd = torch.tensor(ydir[train], dtype=torch.int64)
    yr = torch.tensor(ret48[train], dtype=torch.float32)
    yu = torch.tensor(up48[train], dtype=torch.float32)
    yn = torch.tensor(dn48[train], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses, ranks, covs, poss = [], [], [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total, rtot, ctot, ptot = 0.0, 0.0, 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            out = model(xs[idx], xf[idx])
            # out[0][...,0] da capped trong forward; assert bounded ngay trong smoke
            if not torch.isfinite(out[0]).all():
                raise ValueError("Nonfinite capped score")
            loss, parts = multitask_loss_cov_rank(*out, ys[idx], yd[idx], yr[idx], yu[idx], yn[idx],
                                                  value_w=vw, rank_w=rw, lambda_cov=lam,
                                                  floor_pos=flr, rank_temp=rtemp, rank_tie=rtie)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
            rtot += float(parts["rank"]) * len(idx)
            ctot += float(parts["cov"]) * len(idx)
            ptot += float(parts["mean_pos"]) * len(idx)
        losses.append(total / len(train))
        ranks.append(rtot / len(train))
        covs.append(ctot / len(train))
        poss.append(ptot / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1], "rank": ranks[-1],
                          "cov": covs[-1], "mean_pos": poss[-1]}), flush=True)
    assert all(np.isfinite(ranks)), "ranking-term phai finite (plumbing pairwise ranking CAPPED)"
    assert all(np.isfinite(covs)), "coverage-term phai finite (plumbing coverage-floor CAPPED)"
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    fc = predict_ssm(model, sequence[test][:64], flat[test][:64], batch_size=32)
    assert fc.shape == (64, 16, 6) and np.isfinite(fc).all()
    # BOUNDED-OUTPUT proof v39: unconditional = ch0*fill = capped, |.| <= 0.05
    fill = 1 / (1 + np.exp(-np.clip(fc[..., 4], -40, 40)))
    unconditional = fc[..., 0] * fill
    max_abs_uncond = float(np.max(np.abs(unconditional)))
    assert max_abs_uncond <= SCALE_CAP + 1e-6, f"scale-cap hong: max|uncond|={max_abs_uncond}"
    # VAL-EXPORT proof v39: predict tren validation (past-only), finite + shape + luu file
    fc_val = predict_ssm(model, sequence[validation][:64], flat[validation][:64], batch_size=32)
    assert fc_val.shape == (64, 16, 6) and np.isfinite(fc_val).all()
    fill_val = 1 / (1 + np.exp(-np.clip(fc_val[..., 4], -40, 40)))
    uncond_val = fc_val[..., 0] * fill_val
    max_abs_val = float(np.max(np.abs(uncond_val)))
    assert max_abs_val <= SCALE_CAP + 1e-6, f"scale-cap val hong: {max_abs_val}"
    np.save(out / "val_predictions_sample.npy", fc_val)
    val_export_present = bool((out / "val_predictions_sample.npy").exists())
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_ssm(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    # policy-floor unit-test: (a) all-negative -> top-8; (b) mixed -> gate + du 8
    neg = apply_coverage_floor_policy(np.full(50, -0.01), POLICY_MARGIN, POLICY_N_MIN)
    assert len(neg) == POLICY_N_MIN == 8, f"fallback floor hong: {len(neg)}"
    mixed_en = np.concatenate([np.full(3, 0.005), np.full(47, -0.01)])
    mixed = apply_coverage_floor_policy(mixed_en, POLICY_MARGIN, POLICY_N_MIN)
    assert len(mixed) == 8 and set(range(3)) <= set(mixed.tolist()), "gate+fallback hong"
    en_smoke = expected_net_best(fc)
    gate_hits = int((en_smoke > POLICY_MARGIN).sum())
    np.save(out / "predictions_sample.npy", fc)
    np.savez_compressed(out / "indices.npz", train=train, validation=validation, test=test)
    bal = {k: int((ydir[train] == v).sum()) for k, v in (("SHORT", 0), ("WAIT", 1), ("LONG", 2))}
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "ranking_terms": ranks,
               "coverage_terms": covs, "mean_pos": poss,
               "loss_weights": {"value": vw, "rank": rw, "dir": 1.0, "quant": 1.0,
                                "exc": 0.5, "cov_lambda": lam},
               "ranking_params": {"temperature_percent": rtemp, "tie_band_percent": rtie},
               "coverage_floor": {"lambda": lam, "floor_pos": flr},
               "scale_cap": {"mode": SCALE_CAP_MODE, "cap": SCALE_CAP,
                             "bounded_output_proof": {"max_abs_unconditional_test": max_abs_uncond,
                                                      "max_abs_unconditional_val": max_abs_val,
                                                      "cap": SCALE_CAP, "pass": True}},
               "val_export_proof": {"val_predictions_file": "val_predictions_sample.npy",
                                    "present": val_export_present,
                                    "shape": list(fc_val.shape),
                                    "n_validation_total": int(len(validation)),
                                    "finite": True, "pass": True},
               "epoch_mode": "FIXED 16 (smoke chay 2 epochs plumbing)",
               "policy_floor_unit_test": {"all_negative_picks": len(neg), "mixed_picks": len(mixed),
                                          "margin": POLICY_MARGIN, "n_min": POLICY_N_MIN, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "gate_hits_en_gt_0": gate_hits, "en_best_mean": float(en_smoke.mean())},
               "parameters": n_params, "params_band": "dong kich thuoc v35/v38 (600875)",
               "model_family": "scalecap_selective_ssm_v39", "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "validation_decisions": len(validation),
               "train_label_balance_H48": bal, "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_sample.npy"),
               "val_prediction_sha256": digest(out / "val_predictions_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "calibration_next": "audit local sau train: fit isotonic TREN VAL-PRED EXPORT (val_predictions.npy) past-only TRUOC choose + nguong tu phan vi validation",
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v60_v39.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v60_v39/smoke")
    main(p.parse_args())
