import torch

from agentic_alpha_lab.models.ranked_gate_loss import (
    expected_net_gate_loss,
    ranked_gate_tcn_objective,
)


def test_gate_loss_prefers_scores_on_the_correct_side_of_wait_boundary():
    labels = torch.zeros(1, 2, 3)
    labels[0, :, 0] = torch.tensor([1.0, -1.0])
    good = torch.tensor([[1.0, -1.0]])
    bad = torch.tensor([[-1.0, 1.0]])
    assert expected_net_gate_loss(good, labels) < expected_net_gate_loss(bad, labels)


def test_ranked_gate_objective_has_finite_gradients_on_tied_labels():
    prediction = torch.zeros(2, 16, 2, requires_grad=True)
    auxiliary = torch.zeros(2, requires_grad=True)
    labels = torch.zeros(2, 16, 3)
    labels[..., 1] = 1.0
    loss = ranked_gate_tcn_objective(prediction, auxiliary, labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(prediction.grad).all()
    assert torch.isfinite(auxiliary.grad).all()
