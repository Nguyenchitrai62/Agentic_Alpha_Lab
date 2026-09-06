import torch

from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.models.ranked_loss import ranked_tcn_objective
from agentic_alpha_lab.models.temporal_value import TemporalValue


def test_ranked_gru_forward_and_objective_have_finite_gradients():
    torch.set_num_threads(2)
    candidates = grid({"entry_atr_5m": [.5, 1.5],
                       "brackets_atr_4h": [[2, 2, 4], [3, 3, 6]],
                       "holding_days": [3, 7]})
    model = TemporalValue(candidates, width=12, dropout=0)
    sequence = torch.randn(2, 5, 128, 6)
    features = torch.zeros(2, 40)
    score, auxiliary = model(sequence, features)
    labels = torch.zeros(2, 16, 3)
    labels[..., 1] = 1
    loss = ranked_tcn_objective(score, auxiliary, labels)
    assert score.shape == (2, 16, 2)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(model.history.weight_hh_l0.grad).all()
