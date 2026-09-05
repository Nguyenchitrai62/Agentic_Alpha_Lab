"""Robust candidate-utility losses for the v22 temporal experiment.

The model predicts unconditional expected net percentage for each executable
candidate.  The ranking term is trained only from past-fold labels and keeps a
fixed WAIT action at zero, so it directly tests whether the model can order
actions above abstention without changing the portfolio policy.
"""
import torch
from torch.nn import functional as F


def pairwise_expected_rank_loss(expected, labels, temperature_percent=1.0,
                                tie_band_percent=0.25):
    """Penalize candidate orderings that disagree by more than a fixed tie band.

    ``expected`` is unconditional expected net percentage.  ``labels[..., 0]``
    is already zero for an unfilled candidate, so it is the realized utility
    used for ranking.  A synthetic WAIT action with utility and score zero is
    included as an abstention reference.  The tie band and temperature are
    registered experiment parameters, never fit on evaluation outcomes.
    """
    if expected.ndim != 2 or labels.ndim != 3 or labels.shape[:2] != expected.shape:
        raise ValueError("Expected [batch,candidate] scores and [batch,candidate,3] labels")
    if not torch.isfinite(expected).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite ranking inputs")
    if temperature_percent <= 0 or tie_band_percent < 0:
        raise ValueError("Invalid ranking temperature or tie band")

    realized = labels[..., 0]
    expected = torch.cat((expected, expected.new_zeros((len(expected), 1))), dim=1)
    realized = torch.cat((realized, realized.new_zeros((len(realized), 1))), dim=1)
    target_difference = realized.unsqueeze(-1) - realized.unsqueeze(-2)
    score_difference = expected.unsqueeze(-1) - expected.unsqueeze(-2)
    comparable = target_difference > tie_band_percent
    penalties = F.softplus(-score_difference / temperature_percent)
    return (penalties * comparable).sum() / comparable.sum().clamp_min(1)


def ranked_tcn_objective(prediction, auxiliary, labels, scale_percent=2.0,
                         ranking_weight=0.5, fill_weight=0.1,
                         auxiliary_weight=0.1, ranking_temperature_percent=1.0,
                         ranking_tie_band_percent=0.25):
    """Huber regression plus fixed candidate-order and causal auxiliary losses."""
    if prediction.ndim != 3 or prediction.shape[-1] != 2:
        raise ValueError("Expected temporal score tensor [batch,candidate,2]")
    if labels.shape != (*prediction.shape[:2], 3):
        raise ValueError("Label shape does not match prediction candidates")
    if scale_percent <= 0 or min(ranking_weight, fill_weight, auxiliary_weight) < 0:
        raise ValueError("Invalid ranked-loss weights")
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
    return regression + ranking_weight * ranking + fill_weight * fill + auxiliary_weight * regime
