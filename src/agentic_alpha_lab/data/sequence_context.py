"""Dimensionless window-only sequence encoding; every input candle already closed."""
import numpy as np


def encode_windows(windows):
    w=np.asarray(windows,dtype=np.float64)
    if w.shape!=(5,128,6) or not np.isfinite(w).all() or (w[...,:4]<=0).any() or (w[...,4:]<0).any():
        raise ValueError("Require finite5x128x6 OHLCV windows")
    close=w[...,3]
    # All normalization uses this completed history, not statistics from future rows.
    scale=np.maximum(np.std(np.diff(np.log(close),axis=1),axis=1),.001)
    prices=np.log(w[...,:4]/close[:,-1,None,None])/scale[:,None,None]
    volumes=np.log1p(w[...,4:])-np.log1p(np.median(w[...,4:],axis=1))[:,None,:]
    return np.concatenate((np.clip(prices,-30,30)/10,np.clip(volumes,-10,10)),axis=-1).astype(np.float32)
