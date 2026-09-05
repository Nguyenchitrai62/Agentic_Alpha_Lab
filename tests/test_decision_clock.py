import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.data.decision_clock import decision_indices


ANCHOR = "1970-01-01T00:04:59.999Z"


def test_anchor_is_invariant_to_history_start():
    times = pd.date_range("2025-01-01T00:04:59.999Z", periods=1000, freq="5min")
    shifted = times[50:]
    a = times[decision_indices(times, 72, 50, ANCHOR)]
    b = shifted[decision_indices(shifted, 72, 50, ANCHOR)]
    assert list(a[a >= shifted[0]]) == list(b)
    assert all(t.hour % 6 == 0 and t.minute == 4 for t in b)


def test_legacy_positional_behavior_preserved():
    times = pd.date_range("2025-01-01T04:14:59.999Z", periods=1000, freq="5min")
    np.testing.assert_array_equal(decision_indices(times, 72, 50), np.arange(0, 950, 72))


def test_equivalent_anchor_timezone_and_microsecond_resolution():
    times = pd.date_range("2025-01-01T00:04:59.999Z", periods=200, freq="5min").as_unit("us")
    np.testing.assert_array_equal(decision_indices(times, 72, 10, ANCHOR),
                                  decision_indices(times, 72, 10, "1970-01-01T07:04:59.999+07:00"))


@pytest.mark.parametrize("anchor", ["1970-01-01T00:04:59.999", "1970-01-01T00:05:00Z"])
def test_reject_invalid_anchor(anchor):
    with pytest.raises(ValueError, match="anchor"):
        decision_indices(pd.date_range(ANCHOR, periods=30, freq="5min"), 72, 0, anchor)


def test_reject_gaps_and_preserve_complete_label_horizon():
    times = pd.date_range(ANCHOR, periods=200, freq="5min")
    with pytest.raises(ValueError, match="contiguous"):
        decision_indices(times.delete(20), 72, 0, ANCHOR)
    result = decision_indices(times, 72, 100, ANCHOR)
    assert (result + 100 < len(times)).all()
    assert not len(decision_indices(times, 72, 300, ANCHOR))
