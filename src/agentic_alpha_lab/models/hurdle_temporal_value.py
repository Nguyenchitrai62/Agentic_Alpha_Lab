"""Small causal-GRU hurdle model for fill, win, gain and loss decomposition."""
import numpy as np
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.temporal_value import TemporalValue


class HurdleTemporalValue(TemporalValue):
    """The v13/v26 GRU encoder with four raw outcome heads per candidate."""

    def __init__(self, candidates, width=48, dropout=.15):
        super().__init__(candidates, width=width, dropout=dropout)
        self.score[-1] = torch.nn.Linear(self.score[-1].in_features, 4)


def hurdle_predict(model, sequence, features, batch_size=128):
    """Convert raw hurdle heads to the common six-column trading schema."""
    model.eval()
    device = next(model.parameters()).device
    result = []
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            raw, _ = model(torch.as_tensor(sequence[start:start + batch_size], dtype=torch.float32, device=device),
                           torch.as_tensor(features[start:start + batch_size], dtype=torch.float32, device=device))
            fill = torch.sigmoid(raw[..., 0]).clamp(1e-6, 1 - 1e-6)
            win = torch.sigmoid(raw[..., 1]).clamp(1e-6, 1 - 1e-6)
            gain, loss = F.softplus(raw[..., 2]), F.softplus(raw[..., 3])
            conditional = win * gain - (1 - win) * loss
            output = torch.zeros((*raw.shape[:2], 6), device=device)
            output[..., 0], output[..., 4], output[..., 5] = conditional, torch.logit(fill), torch.logit(win)
            result.append(output.cpu())
    return torch.cat(result).numpy() if result else np.empty((0, len(model.candidates), 6), dtype=np.float32)
