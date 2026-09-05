import torch
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from safetensors.torch import save_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from train_tcn_validated import validation_loss
from audit_tcn_export import verify_epoch_selection
from train_tcn_kaggle import digest
from agentic_alpha_lab.models.temporal_validation import nested_split
from agentic_alpha_lab.models.tcn_fusion_value import TemporalValue
from agentic_alpha_lab.models.macro_micro_value import objective
from agentic_alpha_lab.data.swing import grid


def test_validation_loss_is_sample_weighted_and_does_not_train():
    torch.set_num_threads(2)
    candidates = grid({"entry_atr_5m": [.5, 1.5], "brackets_atr_4h": [[2, 2, 4], [3, 3, 6]], "holding_days": [3, 7]})
    model = TemporalValue(candidates, width=24, tcn_width=8, layers=1, heads=3, dropout=0, dilations=[1])
    x, f, y = torch.randn(5, 5, 128, 6), torch.randn(5, 40), torch.randn(5, 16, 3)
    y[..., 1] = (y[..., 1] > 0).float()
    before = {k: v.clone() for k, v in model.state_dict().items()}
    result = validation_loss(model, x, f, y, batch_size=2)
    with torch.no_grad():
        score, aux = model(x, f)
        expected = objective(score, aux, y).item()
    assert result == pytest.approx(expected, rel=1e-5)
    assert all(torch.equal(value, model.state_dict()[name]) for name, value in before.items())
    assert all(p.grad is None for p in model.parameters())


def test_nested_epoch_audit_verifies_rule_and_immutable_inner_artifacts(tmp_path):
    d = pd.DataFrame({"signal_time": pd.date_range("2021-01-01", "2024-01-01", freq="6h", tz="UTC")})
    d["label_end"] = d.signal_time + pd.Timedelta(days=7)
    spec = {"window_days": 730, "validation_days": 180, "embargo_days": 8,
            "minimum_train": 200, "minimum_validation": 100, "minimum_improvement": .0001, "patience": 5}
    parent = {"folds": [["2024-01-01T00:00Z", "2024-04-01T00:00Z"]]}
    train, val, clock = nested_split(d, parent["folds"][0][0])
    target = tmp_path / "seed1729/selection/fold_0"; target.mkdir(parents=True)
    np.savez_compressed(target / "indices.npz", train=train, validation=val)
    save_file({"fixture": torch.ones(1)}, str(target / "selected.safetensors"))
    record = {"seed": 1729, "fold": 0, "selection_spec": spec, "validation_losses": [3., 2., 2.1],
              "selected_epoch": 2, "clock": clock, "selection_weights_sha256": digest(target / "selected.safetensors")}
    (target / "selection.json").write_text(json.dumps(record))
    meta = {"epoch_selection": spec, "selection_record_sha256": digest(target / "selection.json")}
    plan = {"epoch_selection": spec, "training": {"epochs": 32}}
    settings, files = verify_epoch_selection(plan, tmp_path, d, parent, 1729, 0, meta)
    assert settings["epochs"] == 2 and len(files) == 3
    record["selected_epoch"] = 3
    (target / "selection.json").write_text(json.dumps(record))
    meta["selection_record_sha256"] = digest(target / "selection.json")
    with pytest.raises(ValueError, match="Epoch selection"):
        verify_epoch_selection(plan, tmp_path, d, parent, 1729, 0, meta)
