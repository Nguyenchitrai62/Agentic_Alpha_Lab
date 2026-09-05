"""Past-only nested validation for future deep-model training experiments.

No outer-fold labels participate in epoch/model selection. Validation samples
are also embargoed from the refit date; training labels mature before validation.
"""
import numpy as np
import pandas as pd


def nested_split(decisions, refit_at, window_days=730, validation_days=180,
                 embargo_days=8, minimum_train=200, minimum_validation=100):
    at = pd.Timestamp(refit_at)
    if at.tzinfo is None or embargo_days < 8 or validation_days <= embargo_days or window_days <= validation_days + embargo_days:
        raise ValueError("Invalid nested validation clock/window")
    if not decisions.signal_time.is_monotonic_increasing or decisions.signal_time.duplicated().any():
        raise ValueError("Invalid decision chronology")
    if not (decisions.label_end > decisions.signal_time).all():
        raise ValueError("Invalid label maturity")
    validation_start = at - pd.Timedelta(days=validation_days)
    train_cutoff = validation_start - pd.Timedelta(days=embargo_days)
    validation_cutoff = at - pd.Timedelta(days=embargo_days)
    train = np.flatnonzero(((decisions.signal_time >= at - pd.Timedelta(days=window_days)) &
                            (decisions.label_end < train_cutoff)).to_numpy())
    validation = np.flatnonzero(((decisions.signal_time >= validation_start) &
                                 (decisions.label_end < validation_cutoff)).to_numpy())
    if len(train) < minimum_train or len(validation) < minimum_validation:
        raise ValueError("Insufficient past-only train/validation decisions")
    if np.intersect1d(train, validation).size:
        raise ValueError("Overlapping nested splits")
    record = {"refit_at": str(at), "validation_start": str(validation_start),
              "training_label_cutoff_exclusive": str(train_cutoff),
              "validation_label_cutoff_exclusive": str(validation_cutoff),
              "train_count": len(train), "validation_count": len(validation),
              "latest_train_label_end": str(decisions.iloc[train].label_end.max()),
              "latest_validation_label_end": str(decisions.iloc[validation].label_end.max()),
              "outer_labels_used": False}
    return train, validation, record


def earliest_best_epoch(validation_losses, minimum_improvement=1e-4):
    """Fixed tie rule: first epoch wins unless a later loss improves by epsilon."""
    values = np.asarray(validation_losses, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or minimum_improvement < 0:
        raise ValueError("Invalid validation history")
    best = 0
    for epoch in range(1, len(values)):
        if values[epoch] < values[best] - minimum_improvement:
            best = epoch
    return best + 1
