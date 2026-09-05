"""WAIT-aware listwise utility losses for the v23 temporal experiment.

The action-value head emits one unconditional expected-net score per executable
candidate.  A fixed WAIT score of zero turns the realized candidate utilities
into a soft target distribution, so the loss directly trains top-action versus
abstention selection while the Huber term keeps the score in percentage units.
"""
import torch
from torch.nn import functional as F


def listwise_expected_rank_loss(expected, labels, temperature_percent=1.5,
                                clip_percent=6.0):
    """Cross-entropy between realized-utility and predicted-utility rankings.

    ``labels[..., 0]`` is the causal execution utility in percent, including
    zero for an unfilled candidate.  A synthetic WAIT action with utility and
    predicted score zero is appended.  Utility clipping is fixed in the plan
    and only limits the influence of rare extreme labels; it is not fit from
    evaluation outcomes.
    """
    if expected.ndim != 2 or labels.ndim != 3 or labels.shape[:2] != expected.shape:
        raise ValueError("Expected [batch,candidate] scores and [batch,candidate,3] labels")
    if not torch.isfinite(expected).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite listwise inputs")
    if temperature_percent <= 0 or clip_percent <= 0:
        raise ValueError("Invalid listwise temperature or utility clip")

    realized = labels[..., 0].clamp(-clip_percent, clip_percent)
    realized = torch.cat((realized, realized.new_zeros((len(realized), 1))), dim=1)
    scores = torch.cat((expected, expected.new_zeros((len(expected), 1))), dim=1)
    target = F.softmax(realized / temperature_percent, dim=-1)
    log_probability = F.log_softmax(scores / temperature_percent, dim=-1)
    return -(target * log_probability).sum(-1).mean()


def listwise_tcn_objective(prediction, auxiliary, labels, scale_percent=2.0,
                           listwise_weight=0.25, fill_weight=0.1,
                           auxiliary_weight=0.1,
                           listwise_temperature_percent=1.5,
                           listwise_clip_percent=6.0):
    """Huber payoff plus WAIT-aware listwise ranking and causal auxiliaries."""
    if prediction.ndim != 3 or prediction.shape[-1] != 2:
        raise ValueError("Expected temporal score tensor [batch,candidate,2]")
    if labels.shape != (*prediction.shape[:2], 3):
        raise ValueError("Label shape does not match prediction candidates")
    if (scale_percent <= 0 or
            min(listwise_weight, fill_weight, auxiliary_weight) < 0):
        raise ValueError("Invalid listwise-loss weights")
    prediction, auxiliary, labels = prediction.float(), auxiliary.float(), labels.float()
    target, filled = labels[..., 0], labels[..., 1]
    regression = F.smooth_l1_loss(prediction[..., 0] / scale_percent,
                                  target / scale_percent)
    fill = F.binary_cross_entropy_with_logits(prediction[..., 1], filled)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    regime = F.smooth_l1_loss(auxiliary / scale_percent, direction / scale_percent)
    ranking = listwise_expected_rank_loss(
        prediction[..., 0], labels,
        temperature_percent=listwise_temperature_percent,
        clip_percent=listwise_clip_percent,
    )
    return regression + listwise_weight * ranking + fill_weight * fill + auxiliary_weight * regime
