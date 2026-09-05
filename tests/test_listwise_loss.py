import torch

from agentic_alpha_lab.models.listwise_loss import (
    listwise_expected_rank_loss,
    listwise_tcn_objective,
)


def test_listwise_loss_prefers_realized_top_action_and_wait_reference():
    labels = torch.zeros(1, 3, 3)
    labels[0, :, 0] = torch.tensor([2.0, 0.0, -2.0])
    labels[0, :, 1] = 1.0
    good = torch.tensor([[2.0, 0.0, -2.0]], requires_grad=True)
    bad = torch.tensor([[-2.0, 0.0, 2.0]], requires_grad=True)
    assert listwise_expected_rank_loss(good, labels) < listwise_expected_rank_loss(bad, labels)
    listwise_expected_rank_loss(good, labels).backward()
    assert torch.isfinite(good.grad).all()


def test_listwise_loss_prefers_wait_when_all_candidates_are_negative():
    labels = torch.zeros(1, 2, 3)
    labels[0, :, 0] = torch.tensor([-1.0, -2.0])
    assert listwise_expected_rank_loss(torch.tensor([[-1.0, -2.0]]), labels) < \
        listwise_expected_rank_loss(torch.tensor([[1.0, 2.0]]), labels)


def test_listwise_objective_is_finite_when_every_candidate_is_tied():
    prediction = torch.zeros(2, 16, 2, requires_grad=True)
    auxiliary = torch.zeros(2, requires_grad=True)
    labels = torch.zeros(2, 16, 3)
    labels[..., 1] = 1.0
    loss = listwise_tcn_objective(prediction, auxiliary, labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(prediction.grad).all()
    assert torch.isfinite(auxiliary.grad).all()
