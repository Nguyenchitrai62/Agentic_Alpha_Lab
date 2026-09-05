"""Bounded purged walk-forward search; never opens reserve, freezes one candidate."""
import torch
import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.models.tree_pipeline import export_forests, PortableForest
from agentic_alpha_lab.models.regime_gate import apply_gate
from agentic_alpha_lab.backtest.swing import evaluate


def make_model(parameters, x, y):
    parameters = {k: v for k, v in parameters.items() if k != "kind"}
    return {name: ExtraTreesRegressor(**parameters, random_state=1729, n_jobs=2).fit(x, y[..., column])
            for name, column in (("expected", 0), ("fill", 1))}


def prediction(forests, x):
    expected = forests["expected"].predict(x)
    fill = np.clip(forests["fill"].predict(x), 1e-6, 1 - 1e-6)
    p = np.zeros((*expected.shape, 6), np.float32)
    p[..., 0], p[..., 4] = expected / fill, np.log(fill / (1 - fill))
    return p


def search(a):
    manifest = json.loads((a.dataset / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha256(a.dataset / name) != digest:
            raise ValueError(f"Dataset hash mismatch: {name}")
    if a.output.exists():
        raise FileExistsError("Choose a new experiment")
    a.output.mkdir(parents=True)
    config = json.loads((a.dataset / "config.json").read_text())
    plan = json.loads((a.dataset / "plan.json").read_text())
    decisions = pd.read_parquet(a.dataset / "decisions.parquet")
    candles = pd.read_parquet(a.dataset / "candles.parquet")
    with np.load(a.dataset / "examples.npz", allow_pickle=False) as f:
        features, labels = f["features"], f["labels"]
    records = []
    for model_id, parameters in enumerate(plan["models"]):
        for fold_id, (first, last) in enumerate(plan["folds"]):
            start, end = pd.Timestamp(first), pd.Timestamp(last)
            train_mask = (decisions.label_end < start - pd.Timedelta(days=8)).to_numpy()
            val_mask = ((decisions.signal_time >= start) & (decisions.label_end < end)).to_numpy()
            if train_mask.sum() < 200 or val_mask.sum() < 50:
                raise ValueError("Insufficient fold samples")
            forests = make_model(parameters, features[train_mask], labels[train_mask])
            raw = prediction(forests, features[val_mask])
            part = decisions.loc[val_mask].reset_index(drop=True)
            for gate in plan["regime_gates"]:
                for threshold in plan["minimum_expected_net_percent"]:
                    cfg = deepcopy(config)
                    cfg["policy"]["minimum_expected_net_percent"] = threshold
                    gated = apply_gate(raw, features[val_mask], cfg, gate)
                    report, _, _ = evaluate(gated, part, candles, cfg, f"walk_forward_development_fold_{fold_id}")
                    record = {"model_id": model_id, "fold": fold_id, "gate": gate, "threshold": threshold,
                              "train_rows": int(train_mask.sum()), "evaluation_rows": int(val_mask.sum()),
                              "result": report["result"], "fee_stress": report["fee_stress"], "signals": report["signal_count"]}
                    records.append(record)
                    print(json.dumps({k: record[k] for k in ("model_id", "fold", "gate", "threshold")}
                                     | {"net": record["result"]["total_return"], "dd": record["result"]["max_drawdown"],
                                        "fills": record["result"]["trades"]}), flush=True)
            (a.output / "folds.json").write_text(json.dumps(records, indent=2))
    summaries = []
    for model_id in range(len(plan["models"])):
        for gate in plan["regime_gates"]:
            for threshold in plan["minimum_expected_net_percent"]:
                rows = [r for r in records if r["model_id"] == model_id and r["gate"] == gate and r["threshold"] == threshold]
                net = np.asarray([r["result"]["total_return"] for r in rows])
                dd = np.asarray([r["result"]["max_drawdown"] for r in rows])
                stressed = np.asarray([r["fee_stress"]["total_return"] for r in rows])
                trades = sum(r["result"]["trades"] for r in rows)
                qualifies = bool((dd >= -plan["max_drawdown"]).all() and trades >= 15 and (net > 0).sum() >= 3
                                 and net.mean() > 0 and stressed.mean() > 0)
                summaries.append({"model_id": model_id, "gate": gate, "threshold": threshold,
                                  "mean_fold_net": float(net.mean()), "worst_fold_dd": float(dd.min()),
                                  "fold_net": net.tolist(), "positive_folds": int((net > 0).sum()), "total_trades": trades,
                                  "score": float(net.mean() + dd.mean() - .05 * (net < 0).sum()), "qualifies": qualifies})
    summaries.sort(key=lambda r: r["score"], reverse=True)
    (a.output / "leaderboard.json").write_text(json.dumps(summaries, indent=2))
    eligible = [r for r in summaries if r["qualifies"]]
    if not eligible:
        print("NO_DEVELOPMENT_CANDIDATE: reserve remains unopened", flush=True)
        return
    chosen = eligible[0]
    cfg = deepcopy(config)
    cfg["policy"]["minimum_expected_net_percent"] = chosen["threshold"]
    forests = make_model(plan["models"][chosen["model_id"]], features, labels)
    checkpoint = a.output / "checkpoint"
    export_forests(forests, checkpoint)
    portable = PortableForest(checkpoint)
    np.testing.assert_allclose(portable.predict("expected", features), forests["expected"].predict(features), atol=1e-10)
    _, uncertainty = portable.predict("expected", features, True)
    root = Path(__file__).resolve().parents[1]
    source_files = [*sorted((root / "src").rglob("*.py")), Path(__file__)]
    meta = {"config": cfg, "regime_gate": chosen["gate"], "model": "ExtraTrees regime-gated swing v4",
            "selected": chosen, "research_plan": plan, "dataset_manifest_sha256": sha256(a.dataset / "manifest.json"),
            "checkpoint_sha256": sha256(checkpoint / "forests.npz"), "uncertainty_train_median": float(np.median(uncertainty)),
            "test_opened_at_freeze": False, "former_first_holdout_used_as_development": True,
            "source_hashes": {p.relative_to(root).as_posix(): sha256(p) for p in source_files},
            "approved_for_live": False, "probabilities_calibrated": False, "quantiles_estimated": False}
    (checkpoint / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"selected": chosen, "frozen_checkpoint": str(checkpoint)}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    search(p.parse_args())
