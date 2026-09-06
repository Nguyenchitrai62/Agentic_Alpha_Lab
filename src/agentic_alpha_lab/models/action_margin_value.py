"""Causal GRU with a separate candidate-vs-WAIT action-margin head."""
import numpy as np
import torch
from torch import nn


class ActionMarginValue(nn.Module):
    """Encode five closed-candle frames and emit action and fill logits.

    The action head is intentionally separate from the fill/payoff head.  A
    fixed candidate-minus-WAIT margin is converted to the repository's generic
    six-column prediction schema by ``predict_action_margin``; no future data or
    post-hoc policy fitting is involved.
    """

    def __init__(self, candidates, width=48, dropout=.15):
        super().__init__()
        self.register_buffer("feature_mean", torch.zeros(40))
        self.register_buffer("feature_scale", torch.ones(40))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        self.patch = nn.Sequential(nn.Linear(8 * 6, width), nn.GELU(), nn.LayerNorm(width))
        self.history = nn.GRU(width, width, batch_first=True)
        self.frame_features = nn.Sequential(nn.Linear(8, width), nn.GELU())
        self.macro = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.gate = nn.Linear(width, width)
        self.action = nn.Sequential(nn.Linear(6, width), nn.GELU())
        context = 4 * width
        self.action_logit = nn.Sequential(nn.Linear(context, width), nn.GELU(),
                                          nn.Dropout(dropout), nn.Linear(width, 1))
        self.fill_logit = nn.Sequential(nn.Linear(context, width), nn.GELU(),
                                        nn.Dropout(dropout), nn.Linear(width, 1))
        self.wait_logit = nn.Sequential(nn.Linear(width, width), nn.GELU(),
                                        nn.Dropout(dropout), nn.Linear(width, 1))
        self.regime = nn.Linear(width, 1)

    def _context(self, sequence, features):
        n = len(sequence)
        patches = self.patch(sequence.reshape(n * 5, 16, 48))
        _, hidden = self.history(patches)
        normalized = ((features - self.feature_mean) / self.feature_scale).clamp(-10, 10)
        frames = hidden[-1].reshape(n, 5, -1) + self.frame_features(normalized.reshape(n, 5, 8))
        macro = self.macro(frames[:, 3:].flatten(1))
        micro = self.micro(frames[:, :3].flatten(1)) * self.gate(macro).sigmoid()
        action = self.action(self.candidates / self.candidate_scale)
        count = len(action)
        ma = macro[:, None].expand(-1, count, -1)
        mi = micro[:, None].expand(-1, count, -1)
        ac = action[None].expand(n, -1, -1)
        return macro, torch.cat((ma, mi, ac, (ma + mi) * ac), dim=-1)

    def forward(self, sequence, features):
        macro, context = self._context(sequence, features)
        action_logits = self.action_logit(context).squeeze(-1)
        fill_logits = self.fill_logit(context).squeeze(-1)
        wait_logits = self.wait_logit(macro).squeeze(-1)
        return action_logits, wait_logits, fill_logits, self.regime(macro).squeeze(-1)


def predict_action_margin(model, sequence, features, batch_size=128, margin_scale_percent=1.0):
    """Convert fixed candidate-minus-WAIT margins to the common prediction schema."""
    if margin_scale_percent <= 0:
        raise ValueError("Margin score scale must be positive")
    model.eval()
    device = next(model.parameters()).device
    result = []
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            action, wait, fill_logits, _ = model(
                torch.as_tensor(sequence[start:start + batch_size], dtype=torch.float32, device=device),
                torch.as_tensor(features[start:start + batch_size], dtype=torch.float32, device=device))
            fill = fill_logits.sigmoid().clamp(1e-6, 1 - 1e-6)
            margin = (action - wait[:, None]) * margin_scale_percent
            output = torch.zeros((*margin.shape, 6), device=device)
            output[..., 0], output[..., 4] = margin / fill, torch.logit(fill)
            result.append(output.cpu())
    return torch.cat(result).numpy() if result else np.empty((0, len(model.candidates), 6), dtype=np.float32)
