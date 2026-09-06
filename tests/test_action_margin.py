import torch

from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.models.action_margin_loss import action_margin_objective
from agentic_alpha_lab.models.action_margin_value import ActionMarginValue, predict_action_margin


def candidates():
    return grid({"entry_atr_5m": [.5, 1.5],
                 "brackets_atr_4h": [[2, 2, 4], [3, 3, 6]],
                 "holding_days": [3, 7]})


def test_action_margin_forward_and_prediction_schema():
    torch.manual_seed(33)
    model = ActionMarginValue(candidates(), width=16, dropout=0)
    sequence = torch.randn(3, 5, 128, 6)
    features = torch.randn(3, 40)
    action, wait, fill, auxiliary = model(sequence, features)
    assert action.shape == (3, 16)
    assert wait.shape == (3,)
    assert fill.shape == (3, 16)
    assert auxiliary.shape == (3,)
    output = predict_action_margin(model, sequence.numpy(), features.numpy(),
                                   batch_size=2, margin_scale_percent=1.0)
    assert output.shape == (3, 16, 6)
    assert torch.isfinite(action).all()
    (action.sum() + wait.sum() + fill.sum() + auxiliary.sum()).backward()
    assert torch.isfinite(model.history.weight_hh_l0.grad).all()


def test_action_margin_objective_is_finite_and_trainable():
    torch.manual_seed(34)
    action = torch.randn(5, 4, requires_grad=True)
    wait = torch.randn(5, requires_grad=True)
    fill = torch.randn(5, 4, requires_grad=True)
    auxiliary = torch.randn(5, requires_grad=True)
    labels = torch.randn(5, 4, 3)
    labels[..., 1] = torch.randint(0, 2, (5, 4), dtype=torch.float32)
    loss = action_margin_objective(action, wait, fill, auxiliary, labels)
    assert torch.isfinite(loss)
    loss.backward()
    assert action.grad is not None and wait.grad is not None
    assert torch.isfinite(action.grad).all()
