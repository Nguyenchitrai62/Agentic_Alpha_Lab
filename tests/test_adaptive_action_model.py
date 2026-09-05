import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/train_adaptive_action_model.py"
    spec = importlib.util.spec_from_file_location("adaptive_action_model", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_action_row_order_matches_flattened_label_order():
    value = module().action_features(np.array([[1, 2], [3, 4]]), np.array([[10], [20]]))
    np.testing.assert_array_equal(value, [[1, 2, 10], [1, 2, 20], [3, 4, 10], [3, 4, 20]])


def test_monthly_fit_excludes_unmatured_embargo_and_future_labels():
    frame = pd.DataFrame({"signal_time": pd.to_datetime(["2024-01-01Z".replace("Z", "T00:00:00Z"), "2025-02-01T00:00:00Z", "2025-02-20T00:00:00Z", "2025-03-01T00:00:00Z"], utc=True),
                          "label_end": pd.to_datetime(["2024-01-08T00:00:00Z", "2025-02-08T00:00:00Z", "2025-02-27T00:00:00Z", "2025-03-08T00:00:00Z"], utc=True)})
    mask = module().mature_training_mask(frame, "2025-03-01T00:00:00Z", 365, 8)
    np.testing.assert_array_equal(mask, [False, True, False, False])
