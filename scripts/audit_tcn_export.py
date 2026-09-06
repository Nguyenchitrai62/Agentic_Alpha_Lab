"""Locally replay every forecast from all33cloud checkpoints before backtesting.

No training or cloud calls. A numeric near-match alone is insufficient: the
continuous ensemble policy must generate the same ordered trading instructions.
"""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.models.tcn_fusion_value import TemporalValue as TCNTemporalValue
from agentic_alpha_lab.models.temporal_value import TemporalValue as GRUTemporalValue
from agentic_alpha_lab.models.temporal_value import predict
from agentic_alpha_lab.models.hurdle_temporal_value import HurdleTemporalValue, hurdle_predict
from agentic_alpha_lab.models.residual_temporal_value import ResidualTemporalValue, residual_predict
from agentic_alpha_lab.models.ensemble_value import combine
from agentic_alpha_lab.backtest.swing import swing_signals
from train_tcn_kaggle import digest, fold_indices, load_inputs, stable_evaluation_backend, write_json

ROOT = Path(__file__).resolve().parents[1]


def verify_epoch_selection(plan, source, decisions, parent, seed, fold, meta):
    if not plan.get("epoch_selection"):
        return plan["training"], {}
    from agentic_alpha_lab.models.temporal_validation import nested_split, earliest_best_epoch
    target = source / f"seed{seed}/selection/fold_{fold}"
    record = json.loads((target / "selection.json").read_text())
    spec = plan["epoch_selection"]
    if meta.get("epoch_selection") != spec or record["selection_spec"] != spec:
        raise ValueError("Selection specification changed")
    if meta.get("selection_record_sha256") != digest(target / "selection.json"):
        raise ValueError("Selection record changed")
    if record["seed"] != seed or record["fold"] != fold:
        raise ValueError("Selection model identity mismatch")
    best = earliest_best_epoch(record["validation_losses"], spec["minimum_improvement"])
    if best != record["selected_epoch"] or not 1 <= len(record["validation_losses"]) <= plan["training"]["epochs"]:
        raise ValueError("Epoch selection does not follow registered rule")
    train, val, clock = nested_split(decisions, parent["folds"][fold][0],
        **{k: spec[k] for k in ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")})
    if record["clock"] != clock:
        raise ValueError("Selection chronology mismatch")
    with np.load(target / "indices.npz", allow_pickle=False) as ix:
        np.testing.assert_array_equal(ix["train"], train)
        np.testing.assert_array_equal(ix["validation"], val)
    if digest(target / "selected.safetensors") != record["selection_weights_sha256"]:
        raise ValueError("Inner selected checkpoint changed")
    return dict(plan["training"], epochs=best), {p.relative_to(source).as_posix(): digest(p)
        for p in (target / "selection.json", target / "indices.npz", target / "selected.safetensors")}


def require_complete(summary, plan):
    if summary.get("state") != "complete" or summary.get("worker_exit_codes") != [0, 0] or summary.get("missing_or_failed"):
        raise ValueError("All registered cloud jobs must complete before audit")
    if summary.get("plan") != plan:
        raise ValueError("Export plan differs from registered plan")


def check_numeric(local, cloud):
    if local.shape != cloud.shape or not np.isfinite(local).all() or not np.isfinite(cloud).all():
        raise ValueError("Nonfinite/misaligned replay predictions")
    # Declared before reading cloud outcomes. Do not loosen after an audit fails.
    np.testing.assert_allclose(local, cloud, rtol=1e-3, atol=1e-3)
    return float(np.max(np.abs(local - cloud)))


def check_policy(local, cloud):
    if len(local) != len(cloud):
        raise ValueError("Local/cloud policy alert count differs")
    if not len(local):
        return  # An all-WAIT outcome is valid evidence, not a schema failure.
    columns = ["bar_index", "signal_time", "direction", "entry_limit", "stop_loss",
               "take_profit_1", "take_profit_2", "holding_bars", "leverage"]
    if not set(columns).issubset(local.columns) or not set(columns).issubset(cloud.columns):
        raise ValueError("Unexpected signal schema")
    pd.testing.assert_frame_equal(local[columns].reset_index(drop=True),
                                  cloud[columns].reset_index(drop=True), check_exact=True)


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text())
    family = plan.get("model_family")
    if family not in {"tcn_fusion", "gru_temporal", "gru_hurdle", "gru_residual"}:
        raise ValueError("Unsupported temporal architecture")
    summary = json.loads((a.source / "summary.json").read_text())
    require_complete(summary, plan)
    if a.output.exists():
        raise FileExistsError("Use a new immutable audit directory")
    hashes = json.loads((a.source / "bundle-hashes.json").read_text())
    architecture_name = {
        "tcn_fusion": "src/agentic_alpha_lab/models/tcn_fusion_value.py",
        "gru_temporal": "src/agentic_alpha_lab/models/temporal_value.py",
        "gru_hurdle": "src/agentic_alpha_lab/models/hurdle_temporal_value.py",
        "gru_residual": "src/agentic_alpha_lab/models/residual_temporal_value.py",
    }[family]
    source_names = [a.plan.resolve().relative_to(ROOT).as_posix(), plan["parent_plan"],
                 "src/agentic_alpha_lab/models/tcn_fusion_value.py",
                 "src/agentic_alpha_lab/models/temporal_value.py",
                 "src/agentic_alpha_lab/models/macro_micro_value.py", "scripts/train_tcn_kaggle.py"]
    if family in {"gru_temporal", "gru_hurdle", "gru_residual"}:
        source_names += ["scripts/" + plan["cloud_driver"],
                         "src/agentic_alpha_lab/models/ranked_loss.py"]
    if family == "gru_hurdle":
        source_names += ["src/agentic_alpha_lab/models/hurdle_ranked_loss.py"]
    if family == "gru_residual":
        source_names += ["src/agentic_alpha_lab/models/residual_ranked_loss.py"]
    if plan.get("epoch_selection"):
        source_names += ["scripts/train_tcn_validated.py", "src/agentic_alpha_lab/models/temporal_validation.py"]
    for name in source_names:
        if digest(ROOT / name) != hashes.get(name):
            raise ValueError(f"Export/local source identity mismatch: {name}")
    parent = json.loads(Path(plan["parent_plan"]).read_text())
    sequence, features, labels, decisions, candidates = load_inputs(plan)
    cfg = json.loads((Path(plan["dataset"]) / "config.json").read_text())
    a.output.mkdir(parents=True)
    records, forecast_hashes, weight_hashes, selection_hashes = [], {}, {}, {}
    local_by_seed, cloud_by_seed, indices = [], [], None
    device = a.device
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; choose --device cpu explicitly for inference")
    for seed in plan["seeds"]:
        local_parts, cloud_parts, index_parts = [], [], []
        for fold in range(len(parent["folds"])):
            target = a.source / f"seed{seed}/checkpoints/fold_{fold}"
            meta = json.loads((target / "metadata.json").read_text())
            if meta.get("state") != "complete" or not meta.get("gpu_reload_parity"):
                raise ValueError("Incomplete or parity-failed checkpoint")
            expected_training, selection_files = verify_epoch_selection(plan, a.source, decisions, parent, seed, fold, meta)
            selection_hashes.update(selection_files)
            if meta["network"] != plan["network"] or meta["training"] != expected_training or meta["seed"] != seed or meta["fold"] != fold:
                raise ValueError("Checkpoint experiment mismatch")
            if meta["dataset_manifest_sha256"] != digest(Path(plan["dataset"]) / "manifest.json") or meta["cache_manifest_sha256"] != digest(Path(plan["cache"]) / "manifest.json"):
                raise ValueError("Checkpoint input identity mismatch")
            if meta["model_family"] != family or meta["model_source_sha256"] != hashes[architecture_name]:
                raise ValueError("Checkpoint architecture identity mismatch")
            train, test = fold_indices(decisions, parent, plan["training"], fold)
            with np.load(target / "indices.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["train"], train)
                np.testing.assert_array_equal(saved["test"], test)
            weights = target / "model.safetensors"
            if digest(weights) != meta["weights_sha256"]:
                raise ValueError("Checkpoint weights changed")
            weight_hashes[weights.relative_to(a.source).as_posix()] = digest(weights)
            architecture = {"tcn_fusion": TCNTemporalValue,
                            "gru_temporal": GRUTemporalValue,
                            "gru_hurdle": HurdleTemporalValue,
                            "gru_residual": ResidualTemporalValue}[family]
            model = architecture(candidates, **plan["network"])
            model.load_state_dict(load_file(str(weights)))
            np.testing.assert_array_equal(model.candidates.numpy(), candidates)
            if family == "gru_residual":
                np.testing.assert_allclose(model.candidate_prior.numpy(), labels[train, ..., 0].mean(0),
                                           rtol=1e-5, atol=1e-6)
            np.testing.assert_allclose(model.feature_mean.numpy(), features[train].mean(0), rtol=1e-5, atol=1e-6)
            np.testing.assert_allclose(model.feature_scale.numpy(), np.maximum(features[train].std(0), 1e-6), rtol=1e-5, atol=1e-6)
            model.to(device)
            prediction_path = a.source / f"seed{seed}/temporal_neural/fold_{fold}/predictions.npy"
            if digest(prediction_path) != meta["prediction_sha256"]:
                raise ValueError("Export prediction changed")
            cloud = np.load(prediction_path, allow_pickle=False)
            if cloud.shape != (len(test), 16, 6):
                raise ValueError("Invalid exported prediction shape")
            predictor = {"gru_hurdle": hurdle_predict,
                         "gru_residual": residual_predict}.get(family, predict)
            local = predictor(model, sequence[test], features[test], batch_size=a.batch_size)
            error = check_numeric(local, cloud)
            row = {"seed": seed, "fold": fold, "decisions": len(test), "max_error": error}
            records.append(row)
            forecast_hashes[prediction_path.relative_to(a.source).as_posix()] = digest(prediction_path)
            local_parts.append(local); cloud_parts.append(cloud); index_parts.append(test)
            print(json.dumps(row), flush=True)
            write_json(a.output / "progress.json", {"completed": len(records), "last": row, "state": "auditing"})
            del model
        current = np.concatenate(index_parts)
        if indices is not None:
            np.testing.assert_array_equal(current, indices)
        indices = current
        local_by_seed.append(np.concatenate(local_parts)); cloud_by_seed.append(np.concatenate(cloud_parts))
    from research_temporal_continuous import partition_indices
    np.testing.assert_array_equal(indices, np.concatenate(partition_indices(decisions, parent)))
    local_all, cloud_all = np.stack(local_by_seed), np.stack(cloud_by_seed)
    signal_rows = {}
    for branch in plan["ensemble_branches"]:
        if branch.get("require_direction_agreement"):
            raise ValueError("Register a separate audit before changing ensemble policy")
        local, _ = combine(local_all, branch["penalty"])
        cloud, _ = combine(cloud_all, branch["penalty"])
        clock = decisions.iloc[indices].reset_index(drop=True)
        ls, cs = swing_signals(local, clock, cfg), swing_signals(cloud, clock, cfg)
        # Expected-return estimates can differ numerically, but actual instructions
        # and their clocks must be identical. A changed alert blocks evaluation.
        check_policy(ls, cs)
        signal_rows[branch["name"]] = len(ls)
    result = {"state": "passed", "model_family": family, "device": device, "torch": torch.__version__,
              "batch_size": a.batch_size, "rtol": .001, "atol": .001, "folds": records,
              "source_summary_sha256": digest(a.source / "summary.json"),
              "plan_sha256": digest(a.plan), "dataset_manifest_sha256": digest(Path(plan["dataset"]) / "manifest.json"),
              "prediction_files": forecast_hashes, "weight_files": weight_hashes, "identical_policy_signals": signal_rows,
              "selection_files": selection_hashes,
              "all_forecasts_replayed": True, "independent_test": False, "live_approved": False}
    write_json(a.output / "audit.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/swing_v19_tcn_fusion.json"))
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    p.add_argument("--batch-size", type=int, default=8)
    main(p.parse_args())
