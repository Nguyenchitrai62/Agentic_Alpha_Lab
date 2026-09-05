"""Monotone score calibration using mature out-of-sample labels only."""
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


def eligible_history(decisions, asof, lookback_start, embargo_days=8):
    if embargo_days < 8:
        raise ValueError("Calibration requires at least8days label-end embargo")
    cutoff=pd.Timestamp(asof)-pd.Timedelta(days=embargo_days)
    return ((decisions.signal_time>=pd.Timestamp(lookback_start)) &
            (decisions.signal_time<pd.Timestamp(asof)) &
            (decisions.label_end<cutoff)).to_numpy()


def calibrate(scores, targets, decisions, asof, lookback_start, current_scores):
    mask=eligible_history(decisions,asof,lookback_start)
    x,y=np.asarray(scores)[mask].ravel(),np.asarray(targets)[mask].ravel()
    if mask.sum()<50:
        return np.zeros_like(current_scores),{"warmup":"WAIT","eligible_rows":int(mask.sum())},mask
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Nonfinite calibration inputs")
    model=IsotonicRegression(out_of_bounds="clip").fit(x,y)
    mapped=model.predict(np.asarray(current_scores).ravel()).reshape(current_scores.shape)
    details={"asof":str(asof),"lookback_start":str(lookback_start),"embargo_days":8,
             "eligible_rows":int(mask.sum()),"latest_label_end":str(decisions.loc[mask,"label_end"].max()),
             "x":model.X_thresholds_.tolist(),"y":model.y_thresholds_.tolist(),"warmup":None}
    np.testing.assert_allclose(mapped,np.interp(current_scores,model.X_thresholds_,model.y_thresholds_),atol=1e-12)
    return mapped,details,mask
