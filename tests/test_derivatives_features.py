import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.data.derivatives_features import METRICS,daily_context,asof_features


def example():
    times = pd.date_range("2024-01-01",periods=40*288,freq="5min",tz="UTC")
    frame = pd.DataFrame({"create_time":times})
    for col in METRICS:
        frame[col]=1+np.arange(len(times))/10000
    return frame


def test_unavailable_day_mutations_cannot_change_past_features():
    frame=example()
    times=pd.to_datetime(["2024-01-10T23:59:59Z","2024-01-11T00:00:00Z"],utc=True)
    before=asof_features(daily_context(frame,48),times)[0]
    frame.loc[frame.create_time>=pd.Timestamp("2024-01-10",tz="UTC"),METRICS]=1000
    after=asof_features(daily_context(frame,48),times)[0]
    np.testing.assert_array_equal(before,after)
    assert before.shape==(2,40)


def test_missing_day_is_not_carried_or_backfilled():
    frame=example()
    frame=frame.loc[frame.create_time.dt.floor("D")!=pd.Timestamp("2024-01-08",tz="UTC")]
    features,_,_=asof_features(daily_context(frame),pd.to_datetime(["2024-01-10T12:00:00Z"],utc=True))
    assert (features[0,:20]==0).all()
    assert (features[0,20:]==1).all()


def test_final_row_missing_stays_missing_and_stale_cache_expires():
    frame=example()
    frame.loc[frame.create_time==pd.Timestamp("2024-01-08T23:55:00Z"),METRICS]=np.nan
    times=pd.to_datetime(["2024-01-10T12:00:00Z","2025-01-01T00:00:00Z"],utc=True)
    features,_,_=asof_features(daily_context(frame),times)
    assert (features[:,20:]==1).all()
    with pytest.raises(ValueError,match="48h"):
        daily_context(frame,24)
