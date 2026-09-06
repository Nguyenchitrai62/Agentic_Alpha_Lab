import pytest
import torch

from agentic_alpha_lab.models.top_action_loss import top_action_objective, top_action_targets


def test_top_action_targets_include_wait_class():
    labels = torch.zeros(2, 3, 3)
    labels[0, :, 0] = torch.tensor([0.4, 0.1, -0.2])
    labels[1, :, 0] = torch.tensor([0.2, 0.1, 0.0])
    assert torch.equal(top_action_targets(labels), torch.tensor([0, 3]))


def test_top_action_objective_is_finite():
    torch.manual_seed(7)
    prediction = torch.randn(5, 4, 2, requires_grad=True)
    auxiliary = torch.randn(5, requires_grad=True)
    labels = torch.randn(5, 4, 3)
    labels[..., 1] = torch.randint(0, 2, (5, 4), dtype=torch.float32)
    loss = top_action_objective(prediction, auxiliary, labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert prediction.grad is not None


def test_top_action_rejects_bad_shapes():
    with pytest.raises(ValueError):
        top_action_targets(torch.zeros(3, 4, 2))
