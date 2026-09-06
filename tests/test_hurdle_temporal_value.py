import torch

from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.models.hurdle_ranked_loss import hurdle_ranked_objective
from agentic_alpha_lab.models.hurdle_temporal_value import HurdleTemporalValue, hurdle_predict


def test_hurdle_gru_composes_finite_common_prediction_schema():
    torch.set_num_threads(2)
    candidates = grid({"entry_atr_5m": [.5, 1.5],
                       "brackets_atr_4h": [[2, 2, 4], [3, 3, 6]],
                       "holding_days": [3, 7]})
    model = HurdleTemporalValue(candidates, width=12, dropout=0)
    sequence = torch.randn(2, 5, 128, 6)
    features = torch.zeros(2, 40)
    raw, auxiliary = model(sequence, features)
    labels = torch.zeros(2, 16, 3)
    labels[..., 1] = 1
    labels[..., 2] = 1
    loss = hurdle_ranked_objective(raw, auxiliary, labels)
    assert raw.shape == (2, 16, 4)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(model.history.weight_hh_l0.grad).all()
    prediction = hurdle_predict(model, sequence, features)
    assert prediction.shape == (2, 16, 6)
    assert torch.isfinite(torch.as_tensor(prediction)).all()
