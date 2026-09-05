"""Diagnose learned payoff/fill forecasts versus past-only constant controls.

This is development diagnostics, not another threshold search or a trading
accuracy claim. Run only after the full local checkpoint replay audit passes.
"""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_temporal_continuous import require_tcn_audit
from train_tcn_kaggle import fold_indices, digest, write_json


def forecast_metrics(net, fill, labels):
    target, filled = labels[..., 0], labels[..., 1]
    if net.shape != target.shape or fill.shape != filled.shape:
        raise ValueError("Forecast/label shape mismatch")
    if not all(np.isfinite(x).all() for x in (net, fill, labels)):
        raise ValueError("Nonfinite metrics inputs")
    if not ((fill >= 0) & (fill <= 1)).all():
        raise ValueError("Fill probabilities outside [0,1]")
    buckets = []
    edges = [-np.inf, -.5, 0., .3, 1., 2., np.inf]
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (net >= low) & (net < high)
        if mask.any():
            buckets.append({"lower": float(low) if np.isfinite(low) else None,
                            "upper": float(high) if np.isfinite(high) else None,
                            "candidate_observations": int(mask.sum()),
                            "predicted_net_percent": float(net[mask].mean()),
                            "observed_net_percent": float(target[mask].mean()),
                            "observed_fill_fraction": float(filled[mask].mean())})
    # Rank by action at a decision: can the model distinguish the16 alternatives?
    a = pd.DataFrame(net).rank(axis=1).to_numpy()
    b = pd.DataFrame(target).rank(axis=1).to_numpy()
    a -= a.mean(1, keepdims=True); b -= b.mean(1, keepdims=True)
    denominator = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    valid = denominator > 0
    rank_corr = float(((a * b).sum(1)[valid] / denominator[valid]).mean()) if valid.any() else None
    return {"unconditional_net_mse_percent_squared": float(np.mean((net - target) ** 2)),
            "fill_brier": float(np.mean((fill - filled) ** 2)),
            "net_bias_percent": float(np.mean(net - target)),
            "within_decision_action_rank_correlation": rank_corr,
            "rank_decisions": int(valid.sum()), "fixed_score_buckets": buckets}


def main(a):
    plan = json.loads(a.plan.read_text())
    require_tcn_audit(plan, a.source, a.audit)
    parent = json.loads(Path(plan["parent_plan"]).read_text())
    dataset = Path(plan["dataset"])
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name in ("examples.npz", "decisions.parquet"):
        if digest(dataset / name) != manifest["files"][name]:
            raise ValueError("Input hash mismatch")
    decisions = pd.read_parquet(dataset / "decisions.parquet")
    with np.load(dataset / "examples.npz", allow_pickle=False) as data:
        labels = data["labels"]
    if a.output.exists():
        raise FileExistsError("Immutable diagnostics directory exists")
    a.output.mkdir(parents=True)
    records, ensemble_net, ensemble_fill, truth, control_net, control_fill = [], [], [], [], [], []
    for fold in range(len(parent["folds"])):
        train, test = fold_indices(decisions, parent, plan["training"], fold)
        nets, fills = [], []
        baseline = labels[train].mean(0)
        cn = np.broadcast_to(baseline[:, 0], labels[test, ..., 0].shape)
        cf = np.broadcast_to(baseline[:, 1], cn.shape)
        for seed in plan["seeds"]:
            p = np.load(a.source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy", allow_pickle=False)
            fill = 1 / (1 + np.exp(-p[..., 4]))
            net = p[..., 0] * fill
            nets.append(net); fills.append(fill)
            records.append({"seed": seed, "fold": fold, **forecast_metrics(net, fill, labels[test])})
        mean_net, mean_fill = np.mean(nets, 0), np.mean(fills, 0)
        records.append({"seed": "ensemble_mean", "fold": fold, **forecast_metrics(mean_net, mean_fill, labels[test])})
        records.append({"seed": "past_candidate_constant", "fold": fold, **forecast_metrics(cn, cf, labels[test])})
        ensemble_net.append(mean_net); ensemble_fill.append(mean_fill); truth.append(labels[test])
        control_net.append(cn); control_fill.append(cf)
    y = np.concatenate(truth)
    report = {"fold_metrics": records,
              "ensemble_mean": forecast_metrics(np.concatenate(ensemble_net), np.concatenate(ensemble_fill), y),
              "past_candidate_constant": forecast_metrics(np.concatenate(control_net), np.concatenate(control_fill), y),
              "plan_sha256": digest(a.plan), "audit_sha256": digest(a.audit),
              "independent_test": False, "live_approved": False,
              "note": "Overlapping decisions/candidates are not independent observations. Score buckets are fixed diagnostics, not tuned filters. MSE/Brier/rank correlation are not realized trading win rate. Constant controls use only matured training labels at each fold."}
    write_json(a.output / "summary.json", report)
    write_json(a.output / "plan.json", plan)
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("ensemble_mean", "past_candidate_constant")}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/swing_v19_tcn_fusion.json"))
    p.add_argument("--source", type=Path, default=Path("artifacts/kaggle/v19_download/tcn-training"))
    p.add_argument("--audit", type=Path, default=Path("artifacts/research/v19_local_audit/audit.json"))
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args())
