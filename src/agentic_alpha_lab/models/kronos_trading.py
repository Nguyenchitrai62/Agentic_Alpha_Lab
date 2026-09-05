"""Actual pretrained Kronos trunk + cross-timeframe attention + bracket scoring."""
from __future__ import annotations

from pathlib import Path
import torch
from torch import nn
from agentic_alpha_lab.models.kronos_adapter import _import_kronos
from agentic_alpha_lab.data.kronos_trading import candidates


class KronosWindowEncoder(nn.Module):
    def __init__(self, upstream: Path, weights: Path):
        super().__init__()
        Kronos, _, Tokenizer = _import_kronos(upstream)
        self.tokenizer = Tokenizer.from_pretrained(str((weights / "Kronos-Tokenizer-2k").resolve()))
        self.backbone = Kronos.from_pretrained(str((weights / "Kronos-mini").resolve()))
        self.requires_grad_(False)
        self.eval()

    def forward(self, windows: torch.Tensor, stamps: torch.Tensor) -> torch.Tensor:
        batch, frames, length, _ = windows.shape
        x = windows.reshape(batch * frames, length, 6).float()
        # Each normalization sees only its own closed past window, as in KronosPredictor.
        x = ((x - x.mean(1, keepdim=True)) / (x.std(1, correction=0, keepdim=True) + 1e-5)).clamp(-5, 5)
        with torch.no_grad():
            ids = self.tokenizer.encode(x, half=True)
        trunk = self.backbone
        x = trunk.embedding(ids) + trunk.time_emb(stamps.reshape(batch * frames, length, 5))
        x = trunk.token_drop(x)
        for layer in trunk.transformer:
            x = layer(x)
        x = trunk.norm(x)
        # Last state summarizes the causal token trunk; mean adds broad past context.
        return torch.cat([x[:, -1], x.mean(1)], -1).reshape(batch, frames, -1)


class BracketFusion(nn.Module):
    def __init__(self, encoder_width: int, config: dict):
        super().__init__()
        width = config["model"]["width"]
        nframes = len(config["timeframes"])
        self.project = nn.Sequential(nn.LayerNorm(encoder_width), nn.Linear(encoder_width, width))
        self.timeframe = nn.Parameter(torch.zeros(1, nframes, width))
        nn.init.normal_(self.timeframe, std=0.02)
        self.age = nn.Linear(1, width)
        self.fusion = nn.TransformerEncoderLayer(width, config["model"]["heads"], width * 2,
                                                dropout=config["model"]["dropout"], batch_first=True)
        grid = torch.tensor(candidates(config))
        grid[:, 1] /= 10
        self.register_buffer("candidate_features", grid)
        self.candidate = nn.Linear(5, width)
        self.score = nn.Sequential(nn.LayerNorm(width * 2), nn.Linear(width * 2, width), nn.GELU(),
                                   nn.Dropout(config["model"]["dropout"]), nn.Linear(width, 6))

    def forward(self, embedding: torch.Tensor, ages: torch.Tensor) -> torch.Tensor:
        x = self.project(embedding) + self.timeframe + self.age(ages.unsqueeze(-1))
        x = self.fusion(x).mean(1)
        candidate = self.candidate(self.candidate_features).unsqueeze(0).expand(x.shape[0], -1, -1)
        raw = self.score(torch.cat([x[:, None].expand(-1, candidate.shape[1], -1), candidate], -1))
        median = raw[..., 2]
        lower = median - torch.nn.functional.softplus(raw[..., 1]) * 0.1
        upper = median + torch.nn.functional.softplus(raw[..., 3]) * 0.1
        return torch.stack([raw[..., 0], lower, median, upper, raw[..., 4], raw[..., 5]], -1)


def trading_loss(prediction: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    net = labels[..., 0]
    mean_loss = torch.nn.functional.mse_loss(prediction[..., 0], net)
    delta = net.unsqueeze(-1) - prediction[..., 1:4]
    quantiles = prediction.new_tensor([0.1, 0.5, 0.9])
    pinball = torch.maximum(quantiles * delta, (quantiles - 1) * delta).mean()
    binary = torch.nn.functional.binary_cross_entropy_with_logits(prediction[..., 4:6], labels[..., 1:3])
    return mean_loss + pinball + 0.1 * binary
