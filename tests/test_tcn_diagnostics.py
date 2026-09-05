import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_tcn_value import forecast_metrics


def test_perfect_forecasts_and_constant_rank_have_honest_metrics():
    labels = np.zeros((3, 16, 3), np.float32)
    labels[..., 0] = np.arange(16) / 10
    labels[..., 1] = 1
    metrics = forecast_metrics(labels[..., 0], labels[..., 1], labels)
    assert metrics["unconditional_net_mse_percent_squared"] == 0
    assert metrics["fill_brier"] == 0
    assert metrics["within_decision_action_rank_correlation"] == pytest.approx(1)
    constant = forecast_metrics(np.zeros((3, 16)), labels[..., 1], labels)
    assert constant["within_decision_action_rank_correlation"] is None
    assert constant["rank_decisions"] == 0


def test_diagnostics_reject_invalid_probabilities_and_nonfinite_values():
    labels = np.zeros((3, 16, 3), np.float32)
    with pytest.raises(ValueError, match="outside"):
        forecast_metrics(labels[..., 0], np.ones((3, 16)) * 1.1, labels)
    labels[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="Nonfinite"):
        forecast_metrics(labels[..., 0], labels[..., 1], labels)
