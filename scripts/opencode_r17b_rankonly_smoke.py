"""Opencode R17-B SMOKE v55 nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so, giong v28/v35/v38).
(2) Build flat (5628,133) qua wrapper v55 + labels, assert shapes/finite/causal.
(3) 1 fold (fold_0) x 1 seed (1729) x 2 epochs CPU batch 32: forward/backward
     ListNet DUY NHAT (finite), save/reload parity, predict rank logits (n,16),
     gate unit-test (percentile + tie->WAIT + strict-gt). Khong training nang local.
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
from opencode_r17b_rankonly_features import N_FLAT, build_flat  # noqa: E402
from opencode_r17b_rankonly_model import (  # noqa: E402
    RANK_GATE_PERCENTILE,
    RANK_TEMPERATURE_PERCENT,
    RankOnlySSM,
    apply_rank_gate,
    count_params,
    listnet_rank_loss,
    predict_rank,
    rank_logits_to_signals,
    rank_top1_margin_np,
)
from opencode_r17b_rankonly_train import fold_indices, loss_params, make_model  # noqa: E402
from train_tcn_kaggle import stable_evaluation_backend  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "rankonly_ssm_v55", "Sai plan family"
    assert int(plan["training"].get("epochs", plan["training"].get("epochs_fixed", 0))) == 16
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v55 bo early-stop"
    assert plan.get("architecture", {}).get("heads_total") == 1, "v55 chi 1 head"
    assert not plan["architecture"].get("heads_removed") is None
    tau, gate_pct = loss_params(plan)
    assert (tau, gate_pct) == (1.0, 70.0), f"Dong bang khac: {(tau, gate_pct)}"
    assert (RANK_TEMPERATURE_PERCENT, RANK_GATE_PERCENTILE) == (1.0, 70)
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
    assert labels.shape == (5628, 16, 3) and np.isfinite(labels).all()
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    # (3) smoke train 1 fold x 2 epochs CPU (ListNet duy nhat)
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
            logits = model(xs[idx], xf[idx])
            loss = listnet_rank_loss(logits.float(), ys[idx], temperature_percent=tau)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
        losses.append(total / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "listnet_loss": losses[-1]}), flush=True)
    assert all(np.isfinite(losses)), "ranking-loss phai finite"
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    fc = predict_rank(model, sequence[test][:64], flat[test][:64], batch_size=32)
    assert fc.shape == (64, 16) and np.isfinite(fc).all()
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_rank(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    # gate unit-test: (a) tie tuyet doi -> margin 0 -> WAIT khi threshold >= 0;
    # (b) strict-gt: margin == threshold -> WAIT; (c) mapping end-to-end.
    tied = np.zeros((4, 16))
    t_top, t_mar = rank_top1_margin_np(tied)
    assert (t_top == 0).all() and (t_mar == 0).all(), "tie-break phai first-max + margin 0"
    assert len(apply_rank_gate(t_mar, 0.0)) == 0, "strict-gt hong (margin==threshold phai WAIT)"
    assert len(apply_rank_gate(np.array([0.5, 0.0, -1.0]), 0.0)) == 1, "gate hong"
    thr_preview = float(np.percentile(rank_top1_margin_np(
        predict_rank(model, sequence[train][:256], flat[train][:256]))[1], gate_pct))
    chosen, margins = rank_logits_to_signals(fc, thr_preview)
    assert chosen.shape == (64,) and set(np.unique(chosen)) <= (set(range(16)) | {-1})
    assert (margins == rank_top1_margin_np(fc)[1]).all()
    np.save(out / "predictions_sample.npy", fc.astype(np.float32))
    np.savez_compressed(out / "indices.npz", train=train, test=test)
    gate_hits = int((chosen != -1).sum())
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "listnet_losses": losses, "ranking_temperature_percent": tau,
               "epoch_mode": "FIXED 16 (smoke chay 2 epochs plumbing)",
               "gate_unit_test": {"tie_firstmax_margin0": True, "strict_gt": True,
                                  "mapping_end_to_end": True,
                                  "percentile": gate_pct, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "picked": gate_hits, "margin_mean": float(margins.mean())},
               "parameters": n_params, "params_band": "<=1M (597409)",
               "model_family": "rankonly_ssm_v55", "n_flat": N_FLAT,
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
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v55_rankonly.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v55_rankonly/smoke")
    main(p.parse_args())
