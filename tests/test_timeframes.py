from __future__ import annotations

import pandas as pd

from agentic_alpha_lab.data.timeframes import resample_closed_ohlcv


def test_resample_discards_incomplete_final_bucket() -> None:
    times = pd.date_range("2026-01-01 00:00:00+00:00", periods=7, freq="5min")
    frame = pd.DataFrame(
        {
            "open_time": times,
            "close_time": times + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
            "open": range(100, 107),
            "high": range(101, 108),
            "low": range(99, 106),
            "close": range(100, 107),
            "volume": 1.0,
            "quote_volume": 100.0,
        }
    )
    result = resample_closed_ohlcv(frame, "15min")
    assert len(result) == 2
    assert result.iloc[0]["open"] == 100
    assert result.iloc[0]["high"] == 103
    assert result.iloc[0]["low"] == 99
    assert result.iloc[0]["close"] == 102
    assert result.iloc[0]["volume"] == 3.0
