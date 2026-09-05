"""Explicit UTC decision grid, independent of downloaded history start offsets."""
import numpy as np
import pandas as pd


def decision_indices(close_times, stride, horizon, anchor=None):
    """Legacy positional stride only if anchor omitted; preserve frozen datasets."""
    if not isinstance(stride, int) or isinstance(stride, bool) or stride < 1:
        raise ValueError("Stride must be a positive integer")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 0:
        raise ValueError("Horizon must be a nonnegative integer")
    available = max(0, len(close_times) - horizon)
    if anchor is None:
        return np.arange(0, available, stride, dtype=np.int64)
    start = pd.Timestamp(anchor)
    if start.tzinfo is None:
        raise ValueError("Decision anchor must include a timezone")
    start = start.tz_convert("UTC")
    base = pd.Timedelta(minutes=5)
    offset = base - pd.Timedelta(milliseconds=1)
    if (start.value - offset.value) % base.value:
        raise ValueError("Decision anchor must be an exact 5-minute candle close")
    stamps = pd.DatetimeIndex(close_times)
    if stamps.tz is None:
        raise ValueError("Candle close times must include a timezone")
    stamps = stamps.tz_convert("UTC")
    if stamps.hasnans or stamps.has_duplicates or not stamps.is_monotonic_increasing:
        raise ValueError("Invalid candle timestamps")
    ns = stamps.as_unit("ns").asi8
    if ((ns - offset.value) % base.value).any() or (np.diff(ns) != base.value).any():
        raise ValueError("Candle times must form a contiguous 5-minute grid")
    return np.flatnonzero((ns[:available] - start.value) % (stride * base.value) == 0)
