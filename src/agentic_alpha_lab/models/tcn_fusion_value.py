"""Five causal TCN encoders, cross-frame attention and macro-gated bracket values.

Attention sees only candles closed before the decision. Age is relative within
each frame, not a claim that equal token indices share wall-clock timestamps.
"""
import torch
from torch import nn
from torch.nn import functional as F
from agentic_alpha_lab.models.temporal_value import predict


class CausalBlock(nn.Module):
    def __init__(self, width, dilation, dropout):
        super().__init__()
        self.left = 2 * dilation
        self.convs = nn.ModuleList([nn.Conv1d(width, width, 3, dilation=dilation) for _ in range(2)])
        # LayerNorm per timestamp; never normalize across the temporal axis.
        self.norms = nn.ModuleList([nn.LayerNorm(width) for _ in range(2)])
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        for conv, norm in zip(self.convs, self.norms):
            x = conv(F.pad(x, (self.left, 0)))
            x = self.dropout(F.gelu(norm(x.transpose(1, 2)).transpose(1, 2)))
        return x + residual


class TemporalValue(nn.Module):
    def __init__(self, candidates, width=512, tcn_width=128, dropout=.15, layers=6,
                 heads=8, dilations=(1, 2, 4, 8, 16)):
        super().__init__()
        self.register_buffer("feature_mean", torch.zeros(40))
        self.register_buffer("feature_scale", torch.ones(40))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        self.encoders = nn.ModuleList([
            nn.Sequential(nn.Conv1d(6, tcn_width, 1),
                          *[CausalBlock(tcn_width, d, dropout) for d in dilations])
            for _ in range(5)])
        self.project = nn.Linear(tcn_width, width)
        self.frame_embedding = nn.Parameter(torch.randn(1, 5, 1, width) * .02)
        self.age_embedding = nn.Parameter(torch.randn(1, 1, 16, width) * .02)
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(width, heads, 4 * width, dropout,
                                       activation="gelu", batch_first=True, norm_first=True)
            for _ in range(layers)])
        self.norm = nn.LayerNorm(width)
        self.frame_features = nn.Sequential(nn.Linear(8, width), nn.GELU())
        self.macro = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.gate = nn.Linear(width, width)
        self.action = nn.Sequential(nn.Linear(6, width), nn.GELU())
        self.score = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(), nn.Dropout(dropout), nn.Linear(width, 2))
        self.regime = nn.Linear(width, 1)

    def forward(self, sequence, features):
        if sequence.ndim != 4 or sequence.shape[1:] != (5, 128, 6):
            raise ValueError("Expected [batch, 5, 128, 6] closed-candle contexts")
        n = len(sequence)
        # Sample the last TCN state of each eight-candle patch, preserving16 tokens/frame.
        frames = torch.stack([encoder(sequence[:, i].transpose(1, 2))[:, :, 7::8].transpose(1, 2)
                              for i, encoder in enumerate(self.encoders)], dim=1)
        token = (self.project(frames) + self.frame_embedding + self.age_embedding).reshape(n, 80, -1)
        for layer in self.layers:
            token = layer(token)
        normalized = ((features - self.feature_mean) / self.feature_scale).clamp(-10, 10)
        frame = self.norm(token).reshape(n, 5, 16, -1)[:, :, -1] + self.frame_features(normalized.reshape(n, 5, 8))
        macro = self.macro(frame[:, 3:].flatten(1))
        micro = self.micro(frame[:, :3].flatten(1)) * self.gate(macro).sigmoid()
        action = self.action(self.candidates / self.candidate_scale)
        k = len(action)
        ma, mi, ac = macro[:, None].expand(-1, k, -1), micro[:, None].expand(-1, k, -1), action[None].expand(n, -1, -1)
        return self.score(torch.cat((ma, mi, ac, (ma + mi) * ac), -1)), self.regime(macro).squeeze(-1)
