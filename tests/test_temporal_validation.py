import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.models.temporal_validation import nested_split, earliest_best_epoch


def test_nested_validation_purges_both_boundaries_and_ignores_outer_future():
    decisions = pd.DataFrame({"signal_time": pd.date_range("2021-01-01", "2024-06-01", freq="6h", tz="UTC")})
    decisions["label_end"] = decisions.signal_time + pd.Timedelta(days=7)
    train, validation, record = nested_split(decisions, "2024-01-01T00:00:00Z")
    assert decisions.iloc[train].label_end.max() < pd.Timestamp(record["training_label_cutoff_exclusive"])
    assert decisions.iloc[validation].label_end.max() < pd.Timestamp("2023-12-24T00:00:00Z")
    assert not np.intersect1d(train, validation).size
    changed = decisions.copy()
    changed.loc[changed.signal_time >= pd.Timestamp("2024-01-01T00:00Z"), "label_end"] += pd.Timedelta(days=365)
    other_train, other_val, _ = nested_split(changed, "2024-01-01T00:00Z")
    np.testing.assert_array_equal(train, other_train)
    np.testing.assert_array_equal(validation, other_val)


def test_validation_selection_uses_fixed_earliest_tie_and_rejects_bad_losses():
    assert earliest_best_epoch([3., 2., 2., 2.00001]) == 2
    assert earliest_best_epoch([3., 2., 1.]) == 3
    assert earliest_best_epoch([1., .99999]) == 1
    for losses in ([], [np.nan], [1., np.inf]):
        with pytest.raises(ValueError):
            earliest_best_epoch(losses)


def test_validation_rejects_short_embargo_and_too_small_data():
    decisions = pd.DataFrame({"signal_time": pd.date_range("2023-12-01", periods=10, tz="UTC")})
    decisions["label_end"] = decisions.signal_time + pd.Timedelta(days=7)
    with pytest.raises(ValueError, match="window"):
        nested_split(decisions, "2024-01-01T00:00Z", embargo_days=0)
    with pytest.raises(ValueError, match="Insufficient"):
        nested_split(decisions, "2024-01-01T00:00Z")
