import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_tcn_export import require_complete, check_numeric, check_policy
from research_temporal_continuous import require_tcn_audit
from train_tcn_kaggle import digest


def test_partial_cloud_run_cannot_be_selected_as_a_complete_ensemble():
    with pytest.raises(ValueError, match="All registered"):
        require_complete({"state": "incomplete", "worker_exit_codes": [0, 1]}, {})
    with pytest.raises(ValueError, match="plan differs"):
        require_complete({"state": "complete", "worker_exit_codes": [0, 0], "plan": {"seed": 1}}, {"seed": 2})


def test_numeric_replay_rejects_nonfinite_drift_and_bad_shape():
    x = np.ones((2, 16, 6), np.float32)
    assert check_numeric(x, x.copy()) == 0
    with pytest.raises(ValueError):
        check_numeric(x, x[:1])
    y = x.copy(); y[0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        check_numeric(x, y)
    y = x.copy(); y[0, 0, 0] += .1
    with pytest.raises(AssertionError):
        check_numeric(x, y)


def test_backtest_rejects_unaudited_cloud_export(tmp_path):
    with pytest.raises(ValueError, match="full-forecast audit"):
        require_tcn_audit({"model_family": "tcn_fusion"}, tmp_path, None)
    require_tcn_audit({"model_family": "gru"}, tmp_path, None)


def test_all_wait_is_valid_parity_but_changed_order_is_not():
    empty = pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    check_policy(empty, empty.copy())
    order = pd.DataFrame([{"bar_index": 10, "signal_time": "2023-01-01", "direction": 1,
                          "entry_limit": 100., "stop_loss": 90., "take_profit_1": 110.,
                          "take_profit_2": 120., "holding_bars": 864, "leverage": 1.}])
    check_policy(order, order.copy())
    with pytest.raises(ValueError, match="alert count"):
        check_policy(empty, order)
    changed = order.copy(); changed.loc[0, "entry_limit"] += .00001
    with pytest.raises(AssertionError):
        check_policy(order, changed)


def test_audit_gate_accepts_complete_identity_then_rejects_weight_mutation(tmp_path):
    dataset = tmp_path / "dataset"; dataset.mkdir()
    (dataset / "manifest.json").write_text('{}')
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"folds": [["2023-01-01", "2023-04-01"]]}))
    plan = {"model_family": "tcn_fusion", "dataset": str(dataset), "parent_plan": str(parent),
            "seeds": [1729], "ensemble_branches": [{"name": "mean"}]}
    (tmp_path / "summary.json").write_text(json.dumps({"state": "complete", "plan": plan}))
    pred = "seed1729/temporal_neural/fold_0/predictions.npy"
    weight = "seed1729/checkpoints/fold_0/model.safetensors"
    for name in (pred, weight):
        path = tmp_path / name; path.parent.mkdir(parents=True); path.write_bytes(b"fixture")
    audit = {"state": "passed", "all_forecasts_replayed": True,
             "source_summary_sha256": digest(tmp_path / "summary.json"),
             "dataset_manifest_sha256": digest(dataset / "manifest.json"),
             "folds": [{"seed": 1729, "fold": 0}], "identical_policy_signals": {"mean": 0},
             "prediction_files": {pred: digest(tmp_path / pred)}, "weight_files": {weight: digest(tmp_path / weight)}}
    audit_path = tmp_path / "audit.json"; audit_path.write_text(json.dumps(audit))
    require_tcn_audit(plan, tmp_path, audit_path)
    (tmp_path / weight).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        require_tcn_audit(plan, tmp_path, audit_path)
