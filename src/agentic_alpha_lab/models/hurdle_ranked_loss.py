"""Causal hurdle outcome objective with fixed candidate ranking."""
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss


def _masked_smooth_l1(prediction, target, mask, scale):
    if not mask.any():
        return prediction.sum() * 0
    return F.smooth_l1_loss(prediction[mask] / scale, target[mask] / scale)


def _masked_bce_logits(logits, target, mask):
    if not mask.any():
        return logits.sum() * 0
    return F.binary_cross_entropy_with_logits(logits[mask], target[mask])


def hurdle_ranked_objective(raw, auxiliary, labels, scale_percent=2.0,
                           ranking_weight=0.5, fill_weight=0.1, win_weight=0.1,
                           gain_weight=0.15, loss_weight=0.15,
                           auxiliary_weight=0.1, ranking_temperature_percent=1.0,
                           ranking_tie_band_percent=0.25):
    """Train decomposed outcome heads and rank their composed expected utility."""
    if raw.ndim != 3 or raw.shape[-1] != 4:
        raise ValueError("Expected raw hurdle tensor [batch,candidate,4]")
    if labels.shape != (*raw.shape[:2], 3):
        raise ValueError("Label shape does not match prediction candidates")
    weights = (ranking_weight, fill_weight, win_weight, gain_weight,
               loss_weight, auxiliary_weight)
    if scale_percent <= 0 or min(weights) < 0:
        raise ValueError("Invalid hurdle loss settings")
    raw, auxiliary, labels = raw.float(), auxiliary.float(), labels.float()
    target, filled, positive = labels[..., 0], labels[..., 1] > .5, labels[..., 2] > .5
    fill = torch.sigmoid(raw[..., 0])
    win = torch.sigmoid(raw[..., 1])
    gain, loss = F.softplus(raw[..., 2]), F.softplus(raw[..., 3])
    conditional = win * gain - (1 - win) * loss
    expected = fill * conditional
    payoff = F.smooth_l1_loss(expected / scale_percent, target / scale_percent)
    fill_loss = F.binary_cross_entropy_with_logits(raw[..., 0], filled.float())
    win_loss = _masked_bce_logits(raw[..., 1], positive.float(), filled)
    # The magnitude heads are conditional on an actually filled outcome.
    gain_loss = _masked_smooth_l1(gain, target, filled & positive, scale_percent)
    loss_loss = _masked_smooth_l1(loss, -target, filled & ~positive, scale_percent)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    regime = F.smooth_l1_loss(auxiliary / scale_percent, direction / scale_percent)
    ranking = pairwise_expected_rank_loss(
        expected, labels,
        temperature_percent=ranking_temperature_percent,
        tie_band_percent=ranking_tie_band_percent,
    )
    return (payoff + ranking_weight * ranking + fill_weight * fill_loss +
            win_weight * win_loss + gain_weight * gain_loss +
            loss_weight * loss_loss + auxiliary_weight * regime)
