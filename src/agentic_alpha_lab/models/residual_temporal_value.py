"""Small causal-GRU value model with a fold-local candidate prior."""
import numpy as np
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.temporal_value import TemporalValue


class ResidualTemporalValue(TemporalValue):
    """The v13/v26 encoder trained on residual utility around a causal prior."""

    def __init__(self, candidates, width=48, dropout=.15):
        super().__init__(candidates, width=width, dropout=dropout)
        self.register_buffer("candidate_prior", torch.zeros(len(candidates)))


def residual_predict(model, sequence, features, batch_size=128):
    """Add the persisted prior to the residual score and emit the common schema."""
    model.eval()
    device = next(model.parameters()).device
    result = []
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            raw, _ = model(torch.as_tensor(sequence[start:start + batch_size], dtype=torch.float32, device=device),
                           torch.as_tensor(features[start:start + batch_size], dtype=torch.float32, device=device))
            unconditional = raw[..., 0] + model.candidate_prior[None, None, :]
            fill = torch.sigmoid(raw[..., 1]).clamp(1e-6, 1 - 1e-6)
            output = torch.zeros((*raw.shape[:2], 6), device=device)
            output[..., 0], output[..., 4] = unconditional / fill, torch.logit(fill)
            result.append(output.cpu())
    return torch.cat(result).numpy() if result else np.empty((0, len(model.candidates), 6), dtype=np.float32)
