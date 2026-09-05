from __future__ import annotations

import pandas as pd


def resample_closed_ohlcv(
    candles: pd.DataFrame,
    rule: str,
    base_interval: str = "5min",
) -> pd.DataFrame:
    """Aggregate closed base candles and discard an incomplete final bucket."""
    frame = candles.copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], utc=True)
    frame = frame.sort_values("open_time").set_index("open_time")

    expected = int(pd.Timedelta(rule) / pd.Timedelta(base_interval))
    if expected < 1:
        raise ValueError("Target timeframe must not be shorter than the base interval")

    aggregation = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "close_time": "max",
    }
    grouped = frame.resample(rule, label="left", closed="left", origin="epoch")
    result = grouped.agg(aggregation)
    counts = grouped["close"].count()
    result = result.loc[counts == expected].dropna().reset_index()
    return result
