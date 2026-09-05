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

    ratio = pd.Timedelta(rule) / pd.Timedelta(base_interval)
    expected = int(ratio)
    if expected < 1 or ratio != expected:
        raise ValueError("Target timeframe must be an integer multiple of the base interval")
    if frame.index.has_duplicates:
        raise ValueError("Duplicate base candles")
    if (frame.index.asi8 % pd.Timedelta(base_interval).value != 0).any():
        raise ValueError("Base candles are not aligned to the interval grid")
    if (frame["close_time"].array != frame.index + pd.Timedelta(base_interval) - pd.Timedelta(milliseconds=1)).any():
        raise ValueError("Invalid base candle close times")

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
