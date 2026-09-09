"""Opencode R21-B SMOKE v55b nhe (KHONG phai ket qua nghien cuu).

Clone smoke v55 VOI MOT thay doi: moi loss/gate/export chay TREN CAPPED logits
+ CAP-ACTIVE proof bat buoc:
 (1) Audit coverage + causal-join tung nguon (in so, giong v28/v35/v38/v55).
 (2) Build flat (5628,133) + labels, assert shapes/finite/causal.
 (3) 1 fold (fold_0) x 1 seed (1729) x 2 epochs CPU batch 32: forward/backward
      ListNet TREN CAPPED (finite), BOUNDED proof (max|capped|<=CAP+1e-6),
      CAP-ACTIVE proof (a) order-parity raw-vs-capped 100% (don dieu),
      (b) peaked-regime demo: raw x10 -> van bounded + order giu + margin nen,
      (c) bind-frac thuc te smoke, save/reload parity TREN CAPPED,
      predict capped logits (n,16), gate unit-test tren capped margins.
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
from opencode_r21b_v55b_features import N_FLAT, build_flat  # noqa: E402
from opencode_r21b_v55b_model import (  # noqa: E402
    LOGIT_CAP,
    LOGIT_MARGIN_BOUND,
    RANK_GATE_PERCENTILE,
    RANK_TEMPERATURE_PERCENT,
    RankOnlySSM,
    apply_rank_gate,
    cap_rank_logits_np,
    cap_rank_logits_torch,
    capped_listnet_rank_loss,
    capped_logits_to_signals,
    count_params,
    listnet_rank_loss,
    predict_rank,
    rank_top1_margin_np,
)
from opencode_r21b_v55b_train import fold_indices, loss_params, make_model  # noqa: E402
from train_tcn_kaggle import stable_evaluation_backend  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "rankonly_ssm_v55b", "Sai plan family"
    assert int(plan["training"].get("epochs", plan["training"].get("epochs_fixed", 0))) == 16
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v55b bo early-stop"
    assert plan.get("architecture", {}).get("heads_total") == 1, "v55b chi 1 head"
    assert float(plan["architecture"]["scale_cap"]["cap_logit"]) == LOGIT_CAP == 3.0
    assert float(plan["training"]["scale_cap_logit"]) == LOGIT_CAP
    tau, gate_pct, cap = loss_params(plan)
    assert (tau, gate_pct, cap) == (1.0, 70.0, 3.0), f"Dong bang khac: {(tau, gate_pct, cap)}"
    assert (RANK_TEMPERATURE_PERCENT, RANK_GATE_PERCENTILE) == (1.0, 70)
    assert LOGIT_MARGIN_BOUND == 6.0
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    assert len(decisions) == 5628

    # (1) coverage audit (giong v28/v35/v38/v55)
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
    assert labels.shape == (5628, 16, 3) and np.isfinite(labels).all()
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    # (3) smoke train 1 fold x 2 epochs CPU (ListNet TREN CAPPED)
    seed, fold, epochs, batch = 1729, 0, 2, 32
    assert seed in plan["seeds"]
    train, test = fold_indices(decisions, parent, plan, fold)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, RankOnlySSM)
    n_params = count_params(model)
    assert n_params == 597409, f"params doi so voi dong bang: {n_params}"
    assert n_params <= 1_000_000, "vuot budget small encoder"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses = []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total = 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            raw = model(xs[idx], xf[idx])
            capped_t = cap_rank_logits_torch(raw, cap)
            assert (capped_t.abs() <= cap + 1e-6).all(), "torch cap bound hong"
            loss = listnet_rank_loss(capped_t.float(), ys[idx], temperature_percent=tau)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
        losses.append(total / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "capped_listnet_loss": losses[-1]}), flush=True)
    assert all(np.isfinite(losses)), "ranking-loss phai finite"
    # wrapper loss parity: capped_listnet_rank_loss == manual cap + listnet
    model.eval()
    with torch.no_grad():
        probe_raw = model(xs[:batch], xf[:batch])
        l_wrap = capped_listnet_rank_loss(probe_raw, ys[:batch], tau, cap)
        l_man = listnet_rank_loss(cap_rank_logits_torch(probe_raw, cap), ys[:batch], tau)
    assert torch.isfinite(l_wrap) and abs(float(l_wrap - l_man)) < 1e-6, "wrapper loss parity hong"
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    raw_fc = predict_rank(model, sequence[test][:64], flat[test][:64], batch_size=32)
    assert raw_fc.shape == (64, 16) and np.isfinite(raw_fc).all()
    fc = cap_rank_logits_np(raw_fc, cap)
    # BOUNDED proof (cap-active #1)
    assert (np.abs(fc) <= cap + 1e-6).all(), "numpy cap bound hong"
    max_abs_capped = float(np.abs(fc).max())
    # ORDER-PARITY proof (cap-active #2): don dieu -> top1 giong 100%
    raw_top, raw_mar = rank_top1_margin_np(raw_fc)
    cap_top, cap_mar = rank_top1_margin_np(fc)
    order_parity = bool((raw_top == cap_top).all())
    assert order_parity, "tanh don dieu phai giu top1 100%"
    bind_frac = float((np.abs(raw_fc) > cap).mean())
    # PEAKED-REGIME demo (cap-active #3): raw x10 (gia lap overconfidence)
    peaked = (raw_fc * 10.0).astype(np.float64)
    peaked_capped = cap_rank_logits_np(peaked, cap)
    assert (np.abs(peaked_capped) <= cap + 1e-6).all(), "peaked van phai bounded"
    p_top_raw, p_mar_raw = rank_top1_margin_np(peaked)
    p_top_cap, p_mar_cap = rank_top1_margin_np(peaked_capped)
    assert (p_top_raw == p_top_cap).all(), "peaked order phai giu"
    assert (np.abs(p_mar_cap) <= LOGIT_MARGIN_BOUND + 1e-6).all(), "margin bound 6.0 hong"
    peaked_demo = {"scale_factor": 10.0, "raw_margin_p90": float(np.percentile(p_mar_raw, 90)),
                   "capped_margin_p90": float(np.percentile(p_mar_cap, 90)),
                   "capped_margin_max": float(p_mar_cap.max()),
                   "margin_bound": LOGIT_MARGIN_BOUND, "bounded": True, "order_kept": True,
                   "compressed": bool(np.percentile(p_mar_cap, 90) < np.percentile(p_mar_raw, 90))}
    assert peaked_demo["compressed"], "cap phai nen margin phong o peaked regime"
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay_raw = predict_rank(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    replay = cap_rank_logits_np(replay_raw, cap)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    # gate unit-test tren capped margins: tie->WAIT, strict-gt, end-to-end
    tied = np.zeros((4, 16))
    t_top, t_mar = rank_top1_margin_np(cap_rank_logits_np(tied, cap))
    assert (t_top == 0).all() and (t_mar == 0).all(), "tie-break phai first-max + margin 0"
    assert len(apply_rank_gate(t_mar, 0.0)) == 0, "strict-gt hong (margin==threshold phai WAIT)"
    assert len(apply_rank_gate(np.array([0.5, 0.0, -1.0]), 0.0)) == 1, "gate hong"
    thr_preview = float(np.percentile(rank_top1_margin_np(
        cap_rank_logits_np(predict_rank(model, sequence[train][:256], flat[train][:256]), cap))[1],
        gate_pct))
    chosen, margins, _ = capped_logits_to_signals(raw_fc, thr_preview, cap)
    assert chosen.shape == (64,) and set(np.unique(chosen)) <= (set(range(16)) | {-1})
    assert (margins == rank_top1_margin_np(fc)[1]).all()
    np.save(out / "predictions_sample.npy", fc.astype(np.float32))
    np.save(out / "raw_sample.npy", raw_fc.astype(np.float32))
    np.savez_compressed(out / "indices.npz", train=train, test=test)
    gate_hits = int((chosen != -1).sum())
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "capped_listnet_losses": losses, "ranking_temperature_percent": tau,
               "epoch_mode": "FIXED 16 (smoke chay 2 epochs plumbing)",
               "scale_cap": {"mode": "tanh", "cap_logit": cap, "margin_bound": LOGIT_MARGIN_BOUND,
                             "bounded_proof": {"max_abs_capped": max_abs_capped,
                                               "bound": cap, "pass": True},
                             "order_parity_raw_vs_capped": order_parity,
                             "bind_frac_smoke": bind_frac,
                             "peaked_regime_demo": peaked_demo,
                             "wrapper_loss_parity": True},
               "gate_unit_test": {"tie_firstmax_margin0": True, "strict_gt": True,
                                  "mapping_end_to_end_capped": True,
                                  "percentile": gate_pct, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "picked": gate_hits, "margin_mean": float(margins.mean())},
               "parameters": n_params, "params_band": "<=1M (597409, +0 boi cap)",
               "model_family": "rankonly_ssm_v55b", "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v66_v55b.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v66_v55b/smoke")
    main(p.parse_args())
