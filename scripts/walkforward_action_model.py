"""Frozen v8 model specification across past regimes, with no-market-skill control."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from train_adaptive_action_model import action_features, mature_training_mask, fit_models, predict
from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress


def mean_control(labels, count):
    means = labels.mean(axis=0)
    fill = np.clip(means[:, 1], 1e-6, 1-1e-6)
    prediction = np.zeros((count, len(means), 6), np.float32)
    prediction[..., 0] = means[:, 0] / fill
    prediction[..., 4] = np.log(fill / (1-fill))
    return prediction


def run(a, fit_fn=fit_models, predict_fn=predict, model_branch="shared_action_model", implementation_path=None, fold_provider=None):
    plan = json.loads(a.plan.read_text())
    model_plan_path = Path(plan["model_plan"])
    spec = json.loads(model_plan_path.read_text())
    dataset = Path(plan["dataset"])
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(dataset / name) != digest:
            raise ValueError(f"Data hash mismatch: {name}")
    if a.output.exists():
        raise FileExistsError("Choose a new experiment directory")
    cfg = json.loads((dataset / "config.json").read_text())
    decisions = pd.read_parquet(dataset / "decisions.parquet")
    candles = pd.read_parquet(dataset / "candles.parquet")
    with np.load(dataset / "examples.npz", allow_pickle=False) as f:
        features, labels = f["features"], f["labels"]
    feature_provenance = None
    if plan.get("feature_cache"):
        from agentic_alpha_lab.data.feature_cache import read_aligned_features
        extra, feature_provenance = read_aligned_features(Path(plan["feature_cache"]), dataset, decisions)
        features = np.concatenate((features, extra), axis=1)
    anchor = pd.Timestamp("1970-01-01T00:04:59.999Z")
    if ((decisions.signal_time - anchor) % pd.Timedelta(hours=6) != pd.Timedelta(0)).any():
        raise ValueError("Unexpected legacy decision clock")
    if not decisions.signal_time.is_monotonic_increasing or decisions.signal_time.duplicated().any():
        raise ValueError("Invalid chronology")
    candidates = grid(cfg)
    execution = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"], max_holding_bars=max(cfg["holding_days"])*288)
    a.output.mkdir(parents=True)
    (a.output / "plan.json").write_text(json.dumps(plan, indent=2))
    (a.output / "runner_source.py").write_text(Path(__file__).read_text())
    (a.output / "fit_source.py").write_text(Path(__file__).with_name("train_adaptive_action_model.py").read_text())
    if feature_provenance:
        from agentic_alpha_lab.data import feature_cache
        (a.output / "feature_loader_source.py").write_text(Path(feature_cache.__file__).read_text())
    records = []
    with threadpool_limits(limits=2):
        for fold, (start, end) in enumerate(plan["folds"]):
            train = mature_training_mask(decisions, start, spec["training_window_days"], spec["label_embargo_days"])
            test = ((decisions.signal_time >= pd.Timestamp(start)) & (decisions.label_end < pd.Timestamp(end))).to_numpy()
            if plan.get("complete_evaluation_until"):
                test=((decisions.signal_time>=pd.Timestamp(start))&(decisions.signal_time<pd.Timestamp(end))&
                      (decisions.label_end<pd.Timestamp(plan["complete_evaluation_until"]))).to_numpy()
            if train.sum() < spec["minimum_train_decisions"] or test.sum() < 50 or (train & test).any():
                raise ValueError("Invalid fold sample or overlap")
            if fold_provider is None:
                models = fit_fn(action_features(features[train], candidates), labels[train], spec["model"])
                forecast = predict_fn(models, features[test], candidates)
            else:
                forecast = fold_provider(features, labels, train, test, candidates, a.output, fold)
            forecasts = {model_branch: forecast,
                         "train_candidate_mean": mean_control(labels[train], int(test.sum()))}
            for branch in plan["branches"]:
                prediction = forecasts[branch]
                output = a.output / branch / f"fold_{fold}"
                output.mkdir(parents=True)
                report, signals, trades = evaluate(prediction, decisions.loc[test].reset_index(drop=True), candles, cfg, f"opened_development_fold_{fold}")
                signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
                stressed, stress_trades, diagnostics = run_stress(candles, signals, 100, CostModel(**cfg["costs"]), execution, FillStress(5,5,5,.00055,False))
                expected = prediction[..., 0] / (1 + np.exp(-prediction[..., 4]))
                report.update({"fold": fold, "branch": branch, "start": start, "end": end,
                               "train_count": int(train.sum()), "last_training_label_end": str(decisions.loc[train].label_end.max()),
                               "unconditional_candidate_net_mse": float(np.mean((expected - labels[test,...,0])**2)),
                               "execution_stress": {"result": asdict(stressed), **diagnostics}, "independent_test": False})
                (output / "report.json").write_text(json.dumps(report, indent=2))
                np.save(output / "predictions.npy", prediction)
                signals.to_parquet(output / "signals.parquet", index=False)
                trades.to_csv(output / "trades.csv", index=False)
                pd.DataFrame([asdict(t) for t in stress_trades]).to_csv(output / "stress_trades.csv", index=False)
                records.append(report)
                print(json.dumps({"fold": fold, "branch": branch, "net": report["result"]["total_return"],
                                  "dd": report["result"]["max_drawdown"], "fills": report["result"]["trades"], "stress_net": stressed.total_return}), flush=True)
    summaries = {}
    for branch in plan["branches"]:
        rows = [r for r in records if r["branch"] == branch]
        summaries[branch] = {"mean_fold_net": float(np.mean([r["result"]["total_return"] for r in rows])),
                             "joint_positive_folds": sum(all(r[key]["total_return"] > 0 for key in ("result", "fee_stress")) and r["execution_stress"]["result"]["total_return"] > 0 for r in rows),
                             "worst_scenario_fold_dd": min(min(r["result"]["max_drawdown"], r["fee_stress"]["max_drawdown"], r["execution_stress"]["result"]["max_drawdown"]) for r in rows),
                             "total_fills": sum(r["result"]["trades"] for r in rows)}
    model, control = summaries[model_branch], summaries["train_candidate_mean"]
    advances = model["joint_positive_folds"] >= plan.get("minimum_positive_folds",6) and model["worst_scenario_fold_dd"] >= -.2 and model["total_fills"] >= 30 and model["mean_fold_net"] > control["mean_fold_net"]
    if plan.get("complete_evaluation_until"):
        # Fold-local execution resets can overlap trades. Only the continuous runner
        # can evaluate the single global policy/portfolio, so these are diagnostics.
        advances=False
    summary = {"plan": plan, "model_spec": spec, "config": cfg, "plan_sha256": sha256(a.plan),
               "model_plan_sha256": sha256(model_plan_path), "script_sha256": sha256(Path(__file__)),
               "fit_script_sha256": sha256(Path(__file__).with_name("train_adaptive_action_model.py")),
               "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "summaries": summaries,
               "implementation_sha256": sha256(implementation_path) if implementation_path else None,
               "feature_cache": feature_provenance, "market_feature_count": features.shape[1],
               "advance_to_further_research": advances, "independent_test": False, "live_approved": False,
               "note": "Fold means are not a continuous compounded portfolio return. Gaps and independent resets to100 are explicit. Features and labels can overlap within folds; observations are not IID.", "folds": records}
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2))
    (a.output / "runner_source.py").write_text(Path(__file__).read_text())
    if implementation_path:
        (a.output / "model_source.py").write_text(implementation_path.read_text())
    print(json.dumps({"summaries": summaries, "advances": advances}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=Path("configs/swing_v8_walkforward.json"))
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
