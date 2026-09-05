"""Small supervised reference, not a fine-tuned Kronos checkpoint."""
from __future__ import annotations

import torch  # must precede pandas on Windows
from torch import nn
import numpy as np


class MultiHorizonMLP(nn.Module):
    def __init__(self, features: int, hidden: int, horizons: int):
        super().__init__()
        self.horizons = horizons
        self.network = nn.Sequential(nn.Linear(features, hidden), nn.GELU(),
                                     nn.Linear(hidden, hidden), nn.GELU(), nn.Linear(hidden, horizons * 6))

    def forward(self, inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        outputs = self.network(inputs).reshape(-1, self.horizons, 6)
        center = outputs[..., 4]
        quantiles = torch.stack([center - nn.functional.softplus(outputs[..., 3]), center,
                                 center + nn.functional.softplus(outputs[..., 5])], dim=-1)
        return outputs[..., :3], quantiles  # returns in percent units, not fractions


def objective(logits: torch.Tensor, quantiles: torch.Tensor, classes: torch.Tensor,
              returns: torch.Tensor) -> torch.Tensor:
    error = returns.unsqueeze(-1) - quantiles.float()
    levels = torch.tensor([0.1, 0.5, 0.9], device=error.device)
    pinball = torch.maximum(levels * error, (levels - 1) * error).mean()
    return nn.functional.cross_entropy(logits.float().reshape(-1, 3), classes.reshape(-1)) + pinball


def probabilities(logits: np.ndarray, temperature: float) -> np.ndarray:
    scores = logits.astype(float) / temperature
    scores -= scores.max(axis=-1, keepdims=True)
    exp = np.exp(scores)
    return exp / exp.sum(axis=-1, keepdims=True)


def classification_metrics(probs: np.ndarray, labels: np.ndarray) -> dict:
    probs, labels = probs.reshape(-1, 3), labels.reshape(-1)
    confidence, predicted = probs.max(axis=1), probs.argmax(axis=1)
    correct = predicted == labels
    ece = 0.0
    for lower, upper in zip(np.linspace(0, 1, 11)[:-1], np.linspace(0, 1, 11)[1:]):
        mask = (confidence > lower) & (confidence <= upper)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return {"accuracy": float(correct.mean()),
            "nll": float(-np.log(np.clip(probs[np.arange(len(labels)), labels], 1e-12, 1)).mean()),
            "brier": float(((probs - np.eye(3)[labels]) ** 2).sum(axis=1).mean()), "ece": float(ece)}
