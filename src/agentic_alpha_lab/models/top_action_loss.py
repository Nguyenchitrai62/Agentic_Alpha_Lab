"""Top-action classification loss with an explicit fixed WAIT action.

The target is formed only from mature training labels.  Unlike pairwise or
listwise utility regression, this objective directly teaches the model to
choose the best executable candidate (or WAIT when no candidate clears the
registered utility boundary), while a Huber term keeps the score in percent
units for the unchanged portfolio policy.
"""
import torch
from torch.nn import functional as F


def top_action_targets(labels, minimum_action_percent=0.3):
    """Return the fixed candidate/WAIT class target for each decision."""
    if labels.ndim != 3 or labels.shape[-1] != 3 or not torch.isfinite(labels).all():
        raise ValueError("Expected finite labels [batch,candidate,3]")
    if minimum_action_percent < 0:
        raise ValueError("Minimum action utility must be nonnegative")
    realized = labels[..., 0]
    best_value, best_candidate = realized.max(dim=-1)
    wait = labels.new_full(best_candidate.shape, labels.shape[1], dtype=torch.long)
    return torch.where(best_value >= minimum_action_percent, best_candidate, wait)


def top_action_objective(prediction, auxiliary, labels, scale_percent=2.0,
                         top_action_weight=0.75, regression_weight=1.0,
                         fill_weight=0.1, auxiliary_weight=0.1,
                         minimum_action_percent=0.3,
                         classification_temperature=0.5):
    """Huber payoff + top-action/WAIT CE + fill and direction auxiliaries."""
    if prediction.ndim != 3 or prediction.shape[-1] != 2:
        raise ValueError("Expected temporal score tensor [batch,candidate,2]")
    if labels.shape != (*prediction.shape[:2], 3):
        raise ValueError("Label shape does not match prediction candidates")
    weights = (top_action_weight, regression_weight, fill_weight, auxiliary_weight)
    if scale_percent <= 0 or min(weights) < 0 or classification_temperature <= 0:
        raise ValueError("Invalid top-action loss settings")
    prediction, auxiliary, labels = prediction.float(), auxiliary.float(), labels.float()
    target, filled = labels[..., 0], labels[..., 1]
    expected = prediction[..., 0]
    regression = F.smooth_l1_loss(expected / scale_percent, target / scale_percent)
    # WAIT has a fixed zero score and is never learned from an evaluation row.
    logits = torch.cat((expected, expected.new_zeros((len(expected), 1))), dim=-1)
    target_class = top_action_targets(labels, minimum_action_percent)
    classification = F.cross_entropy(logits / classification_temperature, target_class)
    fill_loss = F.binary_cross_entropy_with_logits(prediction[..., 1], filled)
    midpoint = target.shape[1] // 2
    if midpoint < 1:
        raise ValueError("At least two candidates are required")
    direction = target[:, :midpoint].mean(-1) - target[:, midpoint:].mean(-1)
    regime = F.smooth_l1_loss(auxiliary / scale_percent, direction / scale_percent)
    return (regression_weight * regression + top_action_weight * classification +
            fill_weight * fill_loss + auxiliary_weight * regime)
