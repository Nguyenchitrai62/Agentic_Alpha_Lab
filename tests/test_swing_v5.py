import torch
from agentic_alpha_lab.models.swing_v5 import CandidateUtilityHead, utility_ranking_loss, swing_v5_loss


def test_utility_rank_prefers_profit_over_wait_over_loss():
    labels = torch.tensor([[[3., 1., 1.], [-3., 1., 0.]]])
    good = torch.zeros((1, 2, 6))
    good[..., 4] = 10
    good[..., 0] = torch.tensor([[3., -3.]])
    bad = good.clone()
    bad[..., 0] *= -1
    assert utility_ranking_loss(good, labels) < utility_ranking_loss(bad, labels)


def test_unfilled_hypothetical_profit_cannot_improve_ranking_label():
    labels = torch.tensor([[[99., 0., 0.], [0., 0., 0.]]])
    p = torch.randn((1, 2, 6), requires_grad=True)
    loss = utility_ranking_loss(p, labels)
    assert loss.item() == 0
    loss.backward()
    assert torch.isfinite(p.grad).all()


def test_v5_loss_and_head_have_finite_gradients():
    torch.manual_seed(1729)
    head = CandidateUtilityHead(16, 0.)
    inputs = torch.randn(3, 16, 64, requires_grad=True)
    predictions = head(inputs)
    labels = torch.zeros((3, 16, 3))
    labels[..., 0] = torch.linspace(-4, 4, 16)
    labels[..., 1] = 1
    labels[..., 2] = (labels[..., 0] > 0).float()
    loss = swing_v5_loss(predictions, torch.zeros(3, 2), labels, torch.zeros(3, 2))
    loss.backward()
    assert torch.isfinite(loss)
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in head.parameters())
    assert inputs.grad[..., :48].abs().sum() > 0
    assert inputs.grad[..., 48:].abs().sum() > 0


def test_v5_masked_outcomes_do_not_change_loss_without_fills():
    p = torch.zeros(2, 16, 6, requires_grad=True)
    labels = torch.zeros(2, 16, 3)
    base = swing_v5_loss(p, torch.zeros(2, 2), labels, torch.zeros(2, 2))
    labels[..., 0] = 100
    changed = swing_v5_loss(p, torch.zeros(2, 2), labels, torch.zeros(2, 2))
    torch.testing.assert_close(base, changed)
