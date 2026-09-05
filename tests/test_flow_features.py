import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.data.flow_features import flow_features


def candles():
    times = pd.date_range("2025-01-01T00:00:00Z", periods=288*45, freq="5min")
    return pd.DataFrame({"open_time": times, "close_time": times + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
                         "volume": 10., "quote_volume": 1000., "taker_buy_volume": 6., "num_trades": 20})


def test_flow_features_ignore_future_and_incomplete_daily_bar():
    frame = candles()
    at = pd.Timestamp("2025-02-10T12:04:59.999Z")
    expected, names = flow_features(frame, [at])
    changed = frame.copy()
    changed.loc[changed.close_time > at, "taker_buy_volume"] = 0
    actual, _ = flow_features(changed, [at])
    np.testing.assert_allclose(expected, actual)
    partial = frame.copy()
    partial.loc[partial.open_time >= at.floor("D"), "taker_buy_volume"] = 0
    daily, _ = flow_features(partial, [at])
    np.testing.assert_allclose(expected[:, -8:], daily[:, -8:])
    assert len(names) == 40
    assert expected[0, 0] == pytest.approx(.2)


def test_flow_features_reject_invalid_buy_volume():
    frame = candles()
    frame.loc[0, "taker_buy_volume"] = 100
    with pytest.raises(ValueError, match="exceeds"):
        flow_features(frame, [frame.close_time.iloc[-1]])


def test_flow_features_reject_gap():
    frame = candles().drop(index=100).reset_index(drop=True)
    with pytest.raises(ValueError, match="Gap"):
        flow_features(frame, [frame.close_time.iloc[-1]])
