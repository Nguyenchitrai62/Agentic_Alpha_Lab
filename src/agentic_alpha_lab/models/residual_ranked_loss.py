"""Residual utility objective with a causal candidate prior."""
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss


def residual_ranked_objective(raw, auxiliary, labels, prior, scale_percent=2.0,
                             ranking_weight=0.5, fill_weight=0.1,
                             auxiliary_weight=0.1, ranking_temperature_percent=1.0,
                             ranking_tie_band_percent=0.25):
    """Fit context residuals while ranking prior-plus-residual utility."""
    if raw.ndim != 3 or raw.shape[-1] != 2:
        raise ValueError("Expected temporal residual tensor [batch,candidate,2]")
    if labels.shape != (*raw.shape[:2], 3) or prior.shape != (raw.shape[1],):
        raise ValueError("Residual labels/prior shape mismatch")
    if scale_percent <= 0 or min(ranking_weight, fill_weight, auxiliary_weight) < 0:
        raise ValueError("Invalid residual-ranked loss settings")
    raw, auxiliary, labels, prior = raw.float(), auxiliary.float(), labels.float(), prior.float()
    target, filled = labels[..., 0], labels[..., 1]
    expected = raw[..., 0] + prior[None, :]
    regression = F.smooth_l1_loss(raw[..., 0] / scale_percent,
                                  (target - prior[None, :]) / scale_percent)
    fill = F.binary_cross_entropy_with_logits(raw[..., 1], filled)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    regime = F.smooth_l1_loss(auxiliary / scale_percent, direction / scale_percent)
    ranking = pairwise_expected_rank_loss(
        expected, labels,
        temperature_percent=ranking_temperature_percent,
        tie_band_percent=ranking_tie_band_percent,
    )
    return regression + ranking_weight * ranking + fill_weight * fill + auxiliary_weight * regime
