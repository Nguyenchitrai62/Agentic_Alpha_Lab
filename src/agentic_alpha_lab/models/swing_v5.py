"""Experimental v5: explicit context/candidate interactions and utility ranking.

Keeps the v2 full pretrained trunk. No claim of profitability or trained weights.
Versioned separately to preserve frozen v2/v4 source provenance.
"""
import torch
from torch import nn
from torch.nn import functional as F
from agentic_alpha_lab.models.swing import SwingKronos


class CandidateUtilityHead(nn.Module):
    def __init__(self, width, dropout):
        super().__init__()
        self.width = width
        self.context = nn.Sequential(nn.LayerNorm(width * 3), nn.Linear(width * 3, width), nn.GELU())
        self.candidate_norm = nn.LayerNorm(width)
        self.output = nn.Sequential(nn.LayerNorm(width * 4), nn.Linear(width * 4, width * 2),
                                    nn.GELU(), nn.Dropout(dropout), nn.Linear(width * 2, 6))

    def forward(self, combined):
        context = self.context(combined[..., :self.width * 3])
        candidate = self.candidate_norm(combined[..., self.width * 3:])
        return self.output(torch.cat((context, candidate, context * candidate, context - candidate), dim=-1))


class SwingKronosV5(SwingKronos):
    def __init__(self, upstream, weights, config):
        super().__init__(upstream, weights, config)
        self.score = CandidateUtilityHead(config["model"]["width"], config["model"]["dropout"])


def utility_ranking_loss(prediction, labels, temperature_percent=1.0, tie_band_percent=0.25):
    """Pairwise realized net payoff ranking, including a fixed zero-payoff WAIT.

    Unfilled label payoff is zero, not a hypothetical filled-trade return. All
    labels belong to training. This auxiliary target is noisy, not an oracle policy.
    """
    if temperature_percent <= 0 or tie_band_percent < 0:
        raise ValueError("Invalid ranking parameters")
    expected = prediction[..., 0] * prediction[..., 4].sigmoid()
    realized = labels[..., 0] * labels[..., 1]
    zero = expected.new_zeros((*expected.shape[:-1], 1))
    expected, realized = torch.cat((expected, zero), -1), torch.cat((realized, zero), -1)
    target_difference = realized.unsqueeze(-1) - realized.unsqueeze(-2)
    score_difference = expected.unsqueeze(-1) - expected.unsqueeze(-2)
    comparable = target_difference > tie_band_percent
    penalties = F.softplus(-score_difference / temperature_percent)
    return (penalties * comparable).sum() / comparable.sum().clamp(min=1)


def swing_v5_loss(prediction, auxiliary, labels, returns, return_scale_percent=2.0,
                  ranking_weight=0.5):
    """Robust outcome regression plus fill/win/quantile and ranking objectives.

    Outputs stay in percentage points for existing choose/backtest. The fixed
    scale is a development hyperparameter, NOT volatility or calibrated risk.
    """
    if return_scale_percent <= 0 or ranking_weight < 0:
        raise ValueError("Invalid loss parameters")
    p, auxiliary, labels, returns = prediction.float(), auxiliary.float(), labels.float(), returns.float()
    mask, net = labels[..., 1], labels[..., 0]
    count = mask.sum().clamp(min=1)
    regression = (F.smooth_l1_loss(p[..., 0] / return_scale_percent,
                                  net / return_scale_percent, reduction="none") * mask).sum() / count
    delta = (net[..., None] - p[..., 1:4]) / return_scale_percent
    quantiles = p.new_tensor([0.1, 0.5, 0.9])
    quantile = (torch.maximum(quantiles * delta, (quantiles - 1) * delta).mean(-1) * mask).sum() / count
    fill = F.binary_cross_entropy_with_logits(p[..., 4], mask)
    win = (F.binary_cross_entropy_with_logits(p[..., 5], labels[..., 2], reduction="none") * mask).sum() / count
    regime = F.smooth_l1_loss(auxiliary / return_scale_percent, returns / return_scale_percent)
    ranking = utility_ranking_loss(p, labels)
    return regression + .25 * quantile + .2 * (fill + win) + .1 * regime + ranking_weight * ranking
