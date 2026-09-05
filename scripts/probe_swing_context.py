"""Train-only probe of frozen Kronos context; no test or policy threshold search."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import ExtraTreesRegressor
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.models.tree_pipeline import export_forests, PortableForest
from agentic_alpha_lab.data.training import sha256


def fit_projection(train, count):
    scaler = StandardScaler().fit(train)
    pca = PCA(n_components=count, svd_solver="full", whiten=False).fit(scaler.transform(train))
    return {"mean": scaler.mean_, "scale": scaler.scale_, "pca_mean": pca.mean_, "components": pca.components_}


def project(x, parameters):
    return (((x - parameters["mean"]) / parameters["scale"] - parameters["pca_mean"]) @ parameters["components"].T).astype(np.float32)


def read_context(cache, manifest, split):
    parts = []
    for name in sorted(n for n in manifest["files"] if n.startswith(split + "_")):
        if sha256(cache / name) != manifest["files"][name]:
            raise ValueError(f"Corrupt chunk: {name}")
        with np.load(cache / name, allow_pickle=False) as f:
            parts.append(f["context"])
    result = np.concatenate(parts)
    if len(result) != manifest["rows"][split] or not np.isfinite(result).all():
        raise ValueError("Incomplete cached split")
    return result


def run(a):
    plan = json.loads(a.plan.read_text())
    dataset, cache = Path(plan["dataset"]), Path(plan["cache"])
    manifest = json.loads((dataset / "manifest.json").read_text())
    cached = json.loads((cache / "manifest.json").read_text())
    if cached["state"] != "complete" or cached["dataset_manifest_sha256"] != sha256(dataset / "manifest.json"):
        raise ValueError("Require matching complete feature cache")
    for name, digest in manifest["files"].items():
        if sha256(dataset / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    if a.output.exists():
        raise FileExistsError("Choose new probe output")
    cfg = json.loads((dataset / "config.json").read_text())
    raw, labels, context, decisions = {}, {}, {}, {}
    for split in ("train", "validation", "policy"):
        with np.load(dataset / f"{split}.npz", allow_pickle=False) as f:
            raw[split], labels[split] = f["features"], f["labels"]
        context[split] = read_context(cache, cached, split)
        if len(context[split]) != len(raw[split]):
            raise ValueError("Feature/label row mismatch")
        decisions[split] = pd.read_parquet(dataset / f"{split}_decisions.parquet")
    a.output.mkdir(parents=True)
    projection = fit_projection(context["train"], plan["pca_components"])
    np.savez_compressed(a.output / "context_projection.npz", **projection)
    candles = pd.read_parquet(dataset / "development_candles.parquet")
    execution = ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"], max_holding_bars=max(cfg["holding_days"]) * 288)
    stress = FillStress(5, 5, 5, .00055, False)
    reports = []
    for branch in plan["branches"]:
        if branch not in ("raw40", "raw40_plus_kronos_pca32", "raw40_plus_flow_pca16"):
            raise ValueError("Unknown branch")
        x = {s: raw[s] if branch == "raw40" else np.concatenate((raw[s], project(context[s], projection)), axis=1) for s in raw}
        for seed in plan["seeds"]:
            run_dir = a.output / f"{branch}_seed{seed}"
            run_dir.mkdir()
            forests = {name: ExtraTreesRegressor(**plan["tree"], random_state=seed, n_jobs=2).fit(x["train"], labels["train"][..., column])
                       for name, column in (("expected", 0), ("fill", 1))}
            checkpoint = run_dir / "checkpoint"
            export_forests(forests, checkpoint)
            portable = PortableForest(checkpoint)
            for split in ("validation", "policy"):
                np.testing.assert_allclose(portable.predict("expected", x[split]), forests["expected"].predict(x[split]), atol=1e-10)
                predictions, _ = portable.swing_prediction(x[split])
                report, signals, trades = evaluate(predictions, decisions[split], candles, cfg, f"development_probe_{split}")
                signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
                stress_result, stress_trades, details = run_stress(candles, signals, 100, CostModel(**cfg["costs"]), execution, stress)
                report.update({"branch": branch, "seed": seed, "quantiles_estimated": False, "probabilities_calibrated": False,
                               "execution_stress": {"result": asdict(stress_result), **details}, "independent_test": False})
                reports.append(report)
                (run_dir / f"{split}_report.json").write_text(json.dumps(report, indent=2))
                signals.to_parquet(run_dir / f"{split}_signals.parquet", index=False)
                trades.to_csv(run_dir / f"{split}_trades.csv", index=False)
                pd.DataFrame([asdict(t) for t in stress_trades]).to_csv(run_dir / f"{split}_stress_trades.csv", index=False)
                np.save(run_dir / f"{split}_predictions.npy", predictions)
                print(json.dumps({"branch": branch, "seed": seed, "split": split,
                                  "net": report["result"]["total_return"], "dd": report["result"]["max_drawdown"],
                                  "fills": report["result"]["trades"], "stress_net": stress_result.total_return}), flush=True)
    summary = {}
    for branch in plan["branches"]:
        rows = [r for r in reports if r["branch"] == branch]
        per_seed = {str(seed): sum(r["result"]["trades"] for r in rows if r["seed"] == seed) for seed in plan["seeds"]}
        qualifies = all(r["result"]["total_return"] > 0 and r["fee_stress"]["total_return"] > 0
                        and r["execution_stress"]["result"]["total_return"] > 0
                        and r["result"]["max_drawdown"] >= -.2
                        and r["execution_stress"]["result"]["max_drawdown"] >= -.2 for r in rows)
        summary[branch] = {"all_seeds_development_screen": qualifies and min(per_seed.values()) >= 15,
                           "combined_fills_by_seed": per_seed, "live_approved": False}
    provenance = {"plan": plan, "plan_sha256": sha256(a.plan), "cache_manifest_sha256": sha256(cache / "manifest.json"),
                  "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "script_sha256": sha256(Path(__file__)),
                  "projection_sha256": sha256(a.output / "context_projection.npz"), "config": cfg,
                  "summary": summary, "reports": reports, "state": "complete",
                  "warning": "No test opened. Repeated development research, not independent evidence. For Kronos branch the v5 checkpoint was already validation-selected. No winning-seed selection or live approval."}
    (a.output / "summary.json").write_text(json.dumps(provenance, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/swing_v6_probe.json"))
    p.add_argument("--output", type=Path, required=True)
    run(p.parse_args())
