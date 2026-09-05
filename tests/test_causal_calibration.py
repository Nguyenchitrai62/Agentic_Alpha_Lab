import numpy as np
import pandas as pd
import pytest
from agentic_alpha_lab.models.causal_calibration import calibrate,eligible_history


def fixture():
    t=pd.date_range("2024-01-01",periods=120,freq="D",tz="UTC")
    return pd.DataFrame({"signal_time":t,"label_end":t+pd.Timedelta(days=7)})


def test_mutating_future_labels_cannot_change_current_mapping():
    d=fixture();score=np.tile(np.linspace(-2,2,120)[:,None],(1,16));y=score*.2
    before,_,mask=calibrate(score,y,d,"2024-04-01T00:00:00Z","2024-01-01T00:00:00Z",score[-10:])
    y[~mask]=1e6
    after,record,_=calibrate(score,y,d,"2024-04-01T00:00:00Z","2024-01-01T00:00:00Z",score[-10:])
    np.testing.assert_array_equal(before,after)
    assert pd.Timestamp(record["latest_label_end"])<pd.Timestamp("2024-03-24T00:00:00Z")


def test_boundary_label_and_warmup_are_excluded():
    d=fixture();mask=eligible_history(d,"2024-02-01T00:00:00Z","2024-01-01T00:00:00Z")
    assert not mask[d.label_end==pd.Timestamp("2024-01-24T00:00:00Z")].any()
    scores=np.ones((120,16));out,record,_=calibrate(scores,scores,d,"2024-02-01T00:00:00Z","2024-01-01T00:00:00Z",scores[:5])
    assert not out.any() and record["warmup"]=="WAIT"
    with pytest.raises(ValueError): eligible_history(d,"2024-02-01T00:00:00Z","2024-01-01T00:00:00Z",0)
