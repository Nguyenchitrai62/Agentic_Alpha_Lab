import numpy as np
import torch

from agentic_alpha_lab.models.residual_ranked_loss import residual_ranked_objective
from agentic_alpha_lab.models.residual_temporal_value import ResidualTemporalValue, residual_predict


def test_residual_prior_is_persisted_and_added_to_common_schema():
    candidates = np.zeros((16, 6), dtype=np.float32)
    model = ResidualTemporalValue(candidates)
    model.candidate_prior.copy_(torch.arange(16, dtype=torch.float32))
    sequence = np.zeros((2, 5, 128, 6), dtype=np.float32)
    features = np.zeros((2, 40), dtype=np.float32)
    prediction = residual_predict(model, sequence, features)
    assert prediction.shape == (2, 16, 6)
    assert np.isfinite(prediction).all()
    with torch.no_grad():
        raw, _ = model(torch.zeros(2, 5, 128, 6), torch.zeros(2, 40))
    expected = raw[..., 0].numpy() + np.arange(16, dtype=np.float32)[None]
    actual = prediction[:, :, 0] * (1 / (1 + np.exp(-prediction[:, :, 4])))
    assert np.allclose(actual, expected)


def test_residual_ranked_objective_has_finite_gradient():
    raw = torch.zeros(4, 16, 2, requires_grad=True)
    auxiliary = torch.zeros(4, requires_grad=True)
    labels = torch.zeros(4, 16, 3)
    labels[..., 1] = 1
    prior = torch.linspace(-.2, .2, 16)
    loss = residual_ranked_objective(raw, auxiliary, labels, prior)
    assert torch.isfinite(loss)
    loss.backward()
    assert raw.grad is not None and torch.isfinite(raw.grad).all()
