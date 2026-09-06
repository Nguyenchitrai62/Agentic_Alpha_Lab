"""Loss for the v33 separate candidate-vs-WAIT action head."""
import torch
from torch.nn import functional as F

from agentic_alpha_lab.models.top_action_loss import top_action_targets


def action_margin_objective(action_logits, wait_logits, fill_logits, auxiliary, labels,
                            scale_percent=2.0, margin_scale_percent=1.0,
                            action_weight=1.0, margin_regression_weight=.25,
                            fill_weight=.1, auxiliary_weight=.1,
                            minimum_action_percent=.3,
                            classification_temperature=1.0):
    """Train a free action/WAIT classifier plus calibrated margin and fill heads."""
    if action_logits.ndim != 2 or wait_logits.ndim != 1 or fill_logits.shape != action_logits.shape:
        raise ValueError("Expected action/fill [batch,candidate] and WAIT [batch]")
    if auxiliary.ndim != 1 or labels.shape != (*action_logits.shape, 3):
        raise ValueError("Action-margin labels have the wrong shape")
    if not all(torch.isfinite(x).all() for x in (action_logits, wait_logits, fill_logits, auxiliary, labels)):
        raise ValueError("Nonfinite action-margin inputs")
    weights = (action_weight, margin_regression_weight, fill_weight, auxiliary_weight)
    if (scale_percent <= 0 or margin_scale_percent <= 0 or
            classification_temperature <= 0 or min(weights) < 0):
        raise ValueError("Invalid action-margin loss settings")
    action_logits, wait_logits, fill_logits, auxiliary, labels = (
        x.float() for x in (action_logits, wait_logits, fill_logits, auxiliary, labels))
    target = labels[..., 0]
    target_class = top_action_targets(labels, minimum_action_percent)
    classes = torch.cat((action_logits, wait_logits[:, None]), dim=-1)
    classification = F.cross_entropy(classes / classification_temperature, target_class)
    margin = (action_logits - wait_logits[:, None]) * margin_scale_percent
    regression = F.smooth_l1_loss(margin / scale_percent, target / scale_percent)
    fill = F.binary_cross_entropy_with_logits(fill_logits, labels[..., 1])
    midpoint = target.shape[1] // 2
    if midpoint < 1:
        raise ValueError("At least two candidates are required")
    direction_target = target[:, :midpoint].mean(-1) - target[:, midpoint:].mean(-1)
    direction = F.smooth_l1_loss(auxiliary / scale_percent, direction_target / scale_percent)
    return (action_weight * classification + margin_regression_weight * regression +
            fill_weight * fill + auxiliary_weight * direction)
