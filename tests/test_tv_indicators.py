"""Causality of the v231 TradingView indicator features: values at row i must not change when later bars are removed."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

P = Path(__file__).resolve().parents[1] / "research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py"
spec = importlib.util.spec_from_file_location("tv_indicators", P)
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)


def _bars(n=900, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.01, n))
    l = np.minimum(o, c) * (1 - rng.uniform(0, 0.01, n))
    t = pd.date_range("2021-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open_time": t, "open": o, "high": h, "low": l, "close": c, "volume": rng.uniform(1, 10, n)})


def test_tv_features_are_causal():
    b = _bars()
    full = tv.tv_features(b)
    for cut in (300, 511, 777):
        part = tv.tv_features(b.iloc[:cut].copy())
        a, z = full.iloc[:cut].to_numpy(float), part.to_numpy(float)
        both = ~np.isnan(a) & ~np.isnan(z)
        assert (np.isnan(a) == np.isnan(z)).all()
        assert np.allclose(a[both], z[both], rtol=1e-9, atol=1e-9)


def test_tv_features_coverage():
    x = tv.tv_features(_bars())
    assert list(x.columns) == list(tv.TV)
    assert x.iloc[300:].notna().all().all()
