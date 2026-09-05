"""Shared supervised action-value model; purged chronological online retraining proxy."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress


def action_features(features, candidates):
    features, candidates = np.asarray(features), np.asarray(candidates)
    n, k = len(features), len(candidates)
    return np.concatenate((np.repeat(features, k, axis=0), np.tile(candidates, (n, 1))), axis=1)


def mature_training_mask(decisions, fit_at, window_days, embargo_days):
    at = pd.Timestamp(fit_at)
    if at.tzinfo is None or window_days <= embargo_days or embargo_days < 0:
        raise ValueError("Invalid fit clock/window")
    return ((decisions.label_end < at - pd.Timedelta(days=embargo_days))
            & (decisions.signal_time >= at - pd.Timedelta(days=window_days))).to_numpy()


def fit_models(x, labels, params):
    return {name: HistGradientBoostingRegressor(**params).fit(x, labels[..., column].reshape(-1))
            for name, column in (("net", 0), ("fill", 1))}


def predict(models, features, candidates):
    x = action_features(features, candidates)
    net = models["net"].predict(x).reshape(len(features), len(candidates))
    fill = np.clip(models["fill"].predict(x).reshape(net.shape), 1e-6, 1-1e-6)
    prediction = np.zeros((*net.shape, 6), np.float32)
    prediction[..., 0], prediction[..., 4] = net / fill, np.log(fill / (1-fill))
    return prediction


def run(a):
    plan = json.loads(a.plan.read_text())
    dataset = Path(plan["dataset"])
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(dataset / name) != digest:
            raise ValueError(f"Dataset mismatch: {name}")
    if a.output.exists():
        raise FileExistsError("Choose a new experiment")
    cfg = json.loads((dataset / "config.json").read_text())
    arrays, frames = [], []
    for split in ("train", "validation", "policy"):
        with np.load(dataset / f"{split}.npz", allow_pickle=False) as f:
            arrays.append((f["features"], f["labels"]))
        frames.append(pd.read_parquet(dataset / f"{split}_decisions.parquet").assign(split=split))
    decisions = pd.concat(frames, ignore_index=True)
    x, labels = (np.concatenate([part[i] for part in arrays]) for i in (0, 1))
    if not decisions.signal_time.is_monotonic_increasing or decisions.signal_time.duplicated().any():
        raise ValueError("Decision ordering/overlap invalid")
    candidates = grid(cfg)
    candles = pd.read_parquet(dataset / "development_candles.parquet")
    execution = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"], max_holding_bars=max(cfg["holding_days"]) * 288)
    a.output.mkdir(parents=True)
    (a.output / "plan.json").write_text(json.dumps(plan, indent=2))
    reports = {}
    with threadpool_limits(limits=2):
        for branch in plan["branches"]:
            if branch not in ("static", "monthly"):
                raise ValueError("Unknown retraining policy")
            output = a.output / branch
            output.mkdir()
            prediction = np.full((len(decisions), len(candidates), 6), np.nan, np.float32)
            evaluation_rows = decisions.index[decisions.split != "train"].to_numpy()
            groups = {str(plan["static_fit_at"]): evaluation_rows} if branch == "static" else {
                str(pd.Timestamp(month + "-01T00:00:00Z")): group.index.to_numpy()
                for month, group in decisions.loc[evaluation_rows].groupby(decisions.loc[evaluation_rows].signal_time.dt.strftime("%Y-%m"))}
            provenance = []
            for fit_at, indices in groups.items():
                mask = mature_training_mask(decisions, fit_at, plan["training_window_days"], plan["label_embargo_days"])
                if mask.sum() < plan["minimum_train_decisions"]:
                    raise ValueError("Insufficient mature training decisions")
                if (decisions.signal_time.iloc[indices] < pd.Timestamp(fit_at)).any():
                    raise ValueError("Predictions before fitting clock")
                models = fit_models(action_features(x[mask], candidates), labels[mask], plan["model"])
                prediction[indices] = predict(models, x[indices], candidates)
                record = {"branch": branch, "fit_at": fit_at, "train_decisions": int(mask.sum()), "evaluation_decisions": len(indices),
                          "first_training_signal": str(decisions.loc[mask].signal_time.min()),
                          "last_training_label_end": str(decisions.loc[mask].label_end.max())}
                provenance.append(record)
                (output / "fits.json").write_text(json.dumps(provenance, indent=2))
                print(json.dumps(record), flush=True)
            branch_reports = {}
            for split in ("validation", "policy"):
                mask = (decisions.split == split).to_numpy()
                if not np.isfinite(prediction[mask]).all():
                    raise ValueError("Missing chronological predictions")
                report, signals, trades = evaluate(prediction[mask], decisions.loc[mask].reset_index(drop=True), candles, cfg, f"development_adaptive_{split}")
                signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
                stressed, stress_trades, diagnostics = run_stress(candles, signals, 100, CostModel(**cfg["costs"]), execution, FillStress(5, 5, 5, .00055, False))
                report.update({"branch": branch, "model": "HistGradientBoosting_shared_action_value", "probabilities_calibrated": False,
                               "quantiles_estimated": False, "execution_stress": {"result": asdict(stressed), **diagnostics},
                               "independent_test": False})
                (output / f"{split}_report.json").write_text(json.dumps(report, indent=2))
                signals.to_parquet(output / f"{split}_signals.parquet", index=False)
                trades.to_csv(output / f"{split}_trades.csv", index=False)
                pd.DataFrame([asdict(t) for t in stress_trades]).to_csv(output / f"{split}_stress_trades.csv", index=False)
                np.save(output / f"{split}_predictions.npy", prediction[mask])
                branch_reports[split] = report
                print(json.dumps({"branch": branch, "split": split, "net": report["result"]["total_return"],
                                  "dd": report["result"]["max_drawdown"], "fills": report["result"]["trades"], "stress_net": stressed.total_return}), flush=True)
            selected = all(r["result"]["total_return"] > 0 and r["fee_stress"]["total_return"] > 0
                           and r["execution_stress"]["result"]["total_return"] > 0
                           and r["result"]["max_drawdown"] >= -.2 and r["execution_stress"]["result"]["max_drawdown"] >= -.2
                           for r in branch_reports.values()) and sum(r["result"]["trades"] for r in branch_reports.values()) >= 15
            reports[branch] = {"reports": branch_reports, "development_screen": selected, "live_approved": False}
    result = {"state": "complete", "plan_sha256": sha256(a.plan), "script_sha256": sha256(Path(__file__)),
              "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "config": cfg, "branches": reports,
              "checkpoint_exported": False, "note": "Development trial, reproducible fits/predictions recorded. Export safe deployable checkpoints only if further investigation warranted. Monthly histories contain only fully matured labels; policy remains previously researched, not independent evidence."}
    (a.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({branch: {"development_screen": value["development_screen"]} for branch, value in reports.items()}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/swing_v8_adaptive_model.json"))
    p.add_argument("--output", type=Path, required=True)
    run(p.parse_args())
