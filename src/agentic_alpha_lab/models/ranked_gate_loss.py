"""Pairwise utility ranking with a fixed WAIT/action margin for v25."""
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss


def expected_net_gate_loss(expected, labels, threshold_percent=0.3,
                           temperature_percent=0.5):
    """Separate candidates above the frozen policy utility gate from WAIT."""
    if expected.ndim != 2 or labels.ndim != 3 or labels.shape[:2] != expected.shape:
        raise ValueError("Expected [batch,candidate] scores and [batch,candidate,3] labels")
    if not torch.isfinite(expected).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite gate inputs")
    if temperature_percent <= 0:
        raise ValueError("Invalid gate temperature")
    target = torch.where(labels[..., 0] >= threshold_percent,
                         expected.new_ones(expected.shape),
                         -expected.new_ones(expected.shape))
    margin = expected - threshold_percent
    return F.softplus(-target * margin / temperature_percent).mean()


def ranked_gate_tcn_objective(prediction, auxiliary, labels, scale_percent=2.0,
                              ranking_weight=0.5, gate_weight=0.3,
                              fill_weight=0.1, auxiliary_weight=0.1,
                              ranking_temperature_percent=1.0,
                              ranking_tie_band_percent=0.25,
                              gate_threshold_percent=0.3,
                              gate_temperature_percent=0.5):
    """Huber payoff, pairwise order, fixed threshold margin, and auxiliaries."""
    if prediction.ndim != 3 or prediction.shape[-1] != 2:
        raise ValueError("Expected temporal score tensor [batch,candidate,2]")
    if labels.shape != (*prediction.shape[:2], 3):
        raise ValueError("Label shape does not match prediction candidates")
    if (scale_percent <= 0 or
            min(ranking_weight, gate_weight, fill_weight, auxiliary_weight) < 0):
        raise ValueError("Invalid ranked-gate weights")
    prediction, auxiliary, labels = prediction.float(), auxiliary.float(), labels.float()
    target, filled = labels[..., 0], labels[..., 1]
    regression = F.smooth_l1_loss(prediction[..., 0] / scale_percent,
                                  target / scale_percent)
    fill = F.binary_cross_entropy_with_logits(prediction[..., 1], filled)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    regime = F.smooth_l1_loss(auxiliary / scale_percent, direction / scale_percent)
    ranking = pairwise_expected_rank_loss(
        prediction[..., 0], labels,
        temperature_percent=ranking_temperature_percent,
        tie_band_percent=ranking_tie_band_percent,
    )
    gate = expected_net_gate_loss(
        prediction[..., 0], labels,
        threshold_percent=gate_threshold_percent,
        temperature_percent=gate_temperature_percent,
    )
    return (regression + ranking_weight * ranking + gate_weight * gate +
            fill_weight * fill + auxiliary_weight * regime)
