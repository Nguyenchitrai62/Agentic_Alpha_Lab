import torch

from agentic_alpha_lab.models.ranked_loss import (
    pairwise_expected_rank_loss,
    ranked_tcn_objective,
)


def test_pairwise_loss_prefers_realized_action_order_and_wait_reference():
    labels = torch.zeros(1, 3, 3)
    labels[0, :, 0] = torch.tensor([2.0, 0.0, -2.0])
    labels[0, :, 1] = 1.0
    good = torch.tensor([[2.0, 0.0, -2.0]], requires_grad=True)
    bad = torch.tensor([[-2.0, 0.0, 2.0]], requires_grad=True)
    assert pairwise_expected_rank_loss(good, labels) < pairwise_expected_rank_loss(bad, labels)
    pairwise_expected_rank_loss(good, labels).backward()
    assert torch.isfinite(good.grad).all()


def test_ranked_objective_is_finite_when_every_candidate_is_tied():
    prediction = torch.zeros(2, 16, 2, requires_grad=True)
    auxiliary = torch.zeros(2, requires_grad=True)
    labels = torch.zeros(2, 16, 3)
    labels[..., 1] = 1.0
    loss = ranked_tcn_objective(prediction, auxiliary, labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(prediction.grad).all()
    assert torch.isfinite(auxiliary.grad).all()
