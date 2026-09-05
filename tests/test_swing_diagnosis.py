import importlib.util
from pathlib import Path
import numpy as np
import pytest


def diagnostic():
    path = Path(__file__).resolve().parents[1] / "scripts/diagnose_swing_heads.py"
    spec = importlib.util.spec_from_file_location("diagnose_swing_heads", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.diagnostics


def test_diagnostic_detects_constant_output_and_uses_train_only_mean():
    train = np.ones((10, 2, 3), np.float32)
    train[..., 0] = 2
    labels = train.copy()
    labels[..., 0] = np.arange(10)[:, None]
    prediction = np.zeros((10, 2, 6), np.float32)
    prediction[..., 0] = 2
    result = diagnostic()(train, labels, prediction)
    assert result["relative_mse_improvement_over_train_constant"] == 0
    assert result["median_neural_time_std_percent"] == 0
    assert result["train_conditional_mean_by_candidate_percent"] == [2, 2]
    assert result["actual_candidate_fill_fraction"] == 1


def test_diagnostic_rejects_missing_train_fills():
    train = np.ones((4, 2, 3), np.float32)
    train[:, 0, 1] = 0
    with pytest.raises(ValueError, match="no filled"):
        diagnostic()(train, train, np.zeros((4, 2, 6)))
