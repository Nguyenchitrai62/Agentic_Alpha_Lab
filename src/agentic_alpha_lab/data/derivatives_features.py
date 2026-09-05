"""Daily derivatives context with explicit archive-lag proxy, missing masks, no backfill.

This is a research availability scenario, not verified historical publication data.
All intraday rows from day D become usable together at D+lag (lag>=48h).
"""
import numpy as np
import pandas as pd

METRICS = ["sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
           "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def daily_context(metrics, lag_hours=48):
    if lag_hours < 48 or lag_hours % 24:
        raise ValueError("Use complete-day archive delay of at least48h")
    frame = metrics.copy().sort_values("create_time")
    if frame.empty or frame.create_time.dt.tz is None or frame.create_time.duplicated().any():
        raise ValueError("Require nonempty unique UTC-aware event times")
    frame["create_time"] = frame.create_time.dt.tz_convert("UTC")
    if (frame.create_time != frame.create_time.dt.floor("5min")).any():
        raise ValueError("Off-grid metrics require explicit audit before features")
    day = frame.create_time.dt.floor("D")
    dates = pd.date_range(day.min(), day.max(), freq="D")
    # Missing entire days remain rows of NaNs; shifts cannot jump across calendar gaps.
    count = frame.groupby(day)[METRICS].count().reindex(dates, fill_value=0)
    last_rows = frame.groupby(day).tail(1).set_index(day.loc[frame.groupby(day).tail(1).index])
    last = last_rows[METRICS].reindex(dates)
    # Do not take the last non-null historical value if the actual end-of-day row is missing.
    last = last.where((count >= 274) & (last > 0))
    values = {}
    for column in METRICS[:2]:
        for days in (1,3,7,30):
            values[f"{column}_log_change_{days}d"] = np.log(last[column]/last[column].shift(days))
    for column in METRICS[2:]:
        values[f"{column}_log_level"] = np.log(last[column])
        for days in (1,7):
            values[f"{column}_log_change_{days}d"] = np.log(last[column]/last[column].shift(days))
    result = pd.DataFrame(values,index=dates).replace([np.inf,-np.inf],np.nan)
    result.index.name = "source_day"
    result = result.reset_index()
    result["available_at"] = result.source_day + pd.Timedelta(hours=lag_hours)
    return result


def asof_features(context, signal_times):
    times = pd.DatetimeIndex(signal_times)
    if times.tz is None or not times.is_monotonic_increasing:
        raise ValueError("Need chronologically ordered timezone-aware decisions")
    columns = [c for c in context if c not in ("source_day", "available_at")]
    decision_frame = pd.DataFrame({"signal_time":times})
    joined = pd.merge_asof(decision_frame,context.sort_values("available_at"),left_on="signal_time",right_on="available_at",direction="backward",tolerance=pd.Timedelta(hours=24)-pd.Timedelta(nanoseconds=1))
    raw = joined[columns].to_numpy(float)
    missing = ~np.isfinite(raw)
    values = np.clip(np.where(missing,0,raw),-10,10)
    features = np.concatenate((values,missing.astype(float)),axis=1).astype(np.float32)
    names = columns + [c+"_missing" for c in columns]
    return features,names,joined[["signal_time","source_day","available_at"]]
