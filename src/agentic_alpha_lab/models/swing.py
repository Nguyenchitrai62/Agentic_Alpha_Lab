"""Full Kronos-base trunk fine-tuning with macro context conditioning micro entries."""
from pathlib import Path
import torch
from torch import nn
from torch.utils.checkpoint import checkpoint
from agentic_alpha_lab.models.kronos_adapter import _import_kronos
from agentic_alpha_lab.data.swing import grid


class SwingKronos(nn.Module):
    def __init__(self, upstream: Path, weights: Path, config: dict):
        super().__init__()
        Kronos, _, Tokenizer = _import_kronos(upstream)
        self.tokenizer = Tokenizer.from_pretrained(str((weights / "Kronos-Tokenizer-base").resolve()))
        self.tokenizer.requires_grad_(False).eval()
        base = Kronos.from_pretrained(str((weights / "Kronos-base").resolve()))
        # The task replaces token-prediction heads, but fine-tunes ALL trunk blocks/embeddings.
        self.embedding, self.time_emb = base.embedding, base.time_emb
        self.blocks, self.norm, self.token_drop = base.transformer, base.norm, base.token_drop
        width = config["model"]["width"]
        heads = config["model"]["heads"]
        dropout = config["model"]["dropout"]
        self.project = nn.Sequential(nn.LayerNorm(base.d_model * 2), nn.Linear(base.d_model * 2, width))
        self.timeframe = nn.Parameter(torch.randn(1, 5, width) * 0.02)
        self.age = nn.Linear(1, width)
        self.macro = nn.TransformerEncoderLayer(width, heads, width * 2, dropout, batch_first=True)
        self.entry_attention = nn.MultiheadAttention(width, heads, dropout=dropout, batch_first=True)
        self.micro = nn.TransformerEncoderLayer(width, heads, width * 2, dropout, batch_first=True)
        self.features = nn.Sequential(nn.Linear(40, width), nn.GELU())
        candidate = torch.tensor(grid(config))
        candidate[:, -1] /= 7
        self.register_buffer("candidate_grid", candidate)
        self.candidate = nn.Linear(6, width)
        self.score = nn.Sequential(nn.LayerNorm(width * 4), nn.Linear(width * 4, width), nn.GELU(),
                                   nn.Dropout(dropout), nn.Linear(width, 6))
        self.medium_return = nn.Linear(width, 2)
        self.gradient_checkpointing = True

    def train(self, mode=True):
        super().train(mode)
        self.tokenizer.eval()
        return self

    def forward(self, windows, stamps, ages, features):
        batch, frames, length, _ = windows.shape
        x = windows.reshape(batch * frames, length, 6).float()
        # Keep discrete tokenization stable in FP32; no future in the normalization.
        with torch.no_grad(), torch.autocast(device_type=x.device.type, enabled=False):
            x = ((x - x.mean(1, keepdim=True)) / (x.std(1, correction=0, keepdim=True) + 1e-5)).clamp(-5, 5)
            ids = self.tokenizer.encode(x, half=True)
        x = self.token_drop(self.embedding(ids) + self.time_emb(stamps.reshape(batch * frames, length, 5)))
        for block in self.blocks:
            x = checkpoint(block, x, use_reentrant=False) if self.training and self.gradient_checkpointing else block(x)
        x = self.norm(x)
        x = torch.cat([x[:, -1], x.mean(1)], -1).reshape(batch, frames, -1)
        x = self.project(x) + self.timeframe + self.age(ages.unsqueeze(-1))
        macro = self.macro(x[:, 3:])  # closed 4h + 1d regime
        micro = x[:, :3]  # closed 5m + 15m + 1h entry timing
        conditioned, _ = self.entry_attention(micro, macro, macro, need_weights=False)
        micro = self.micro(micro + conditioned).mean(1)
        macro = macro.mean(1)
        context = torch.cat([macro, micro, self.features(features)], -1)
        candidate = self.candidate(self.candidate_grid)[None].expand(batch, -1, -1)
        raw = self.score(torch.cat([context[:, None].expand(-1, candidate.shape[1], -1), candidate], -1))
        median = raw[..., 2]
        low = median - torch.nn.functional.softplus(raw[..., 1])
        high = median + torch.nn.functional.softplus(raw[..., 3])
        prediction = torch.stack([raw[..., 0], low, median, high, raw[..., 4], raw[..., 5]], -1)
        return prediction, self.medium_return(macro)


def swing_loss(prediction, auxiliary, labels, returns):
    p, auxiliary, labels, returns = prediction.float(), auxiliary.float(), labels.float(), returns.float()
    mask, net = labels[..., 1], labels[..., 0]
    count = mask.sum().clamp(min=1)
    mean = ((p[..., 0] - net).square() * mask).sum() / count
    delta = net[..., None] - p[..., 1:4]
    q = p.new_tensor([0.1, 0.5, 0.9])
    quantile = (torch.maximum(q * delta, (q - 1) * delta).mean(-1) * mask).sum() / count
    fill = torch.nn.functional.binary_cross_entropy_with_logits(p[..., 4], mask)
    win = (torch.nn.functional.binary_cross_entropy_with_logits(p[..., 5], labels[..., 2], reduction="none") * mask).sum() / count
    regime = torch.nn.functional.smooth_l1_loss(auxiliary, returns)
    return mean + 0.5 * quantile + 0.2 * (fill + win) + 0.1 * regime
