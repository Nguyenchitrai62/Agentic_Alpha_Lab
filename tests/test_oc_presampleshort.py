"""Tests for oc_presampleshort: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MOD = HERE.parent / "research/tournament/oc_presampleshort/compute_presampleshort.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_presampleshort_mod", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


def _toy_opens(n=500, seed=3) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    rets = 0.001 * np.sin(np.arange(n) / 9.0) + 0.002 * rng.standard_normal(n)
    opens = 100.0 * np.cumprod(1 + rets)
    return pd.Series(opens, index=idx)


def test_sigma_is_causal_trailing_only():
    o = _toy_opens()
    s = M.sigma_series(o)
    # hand-check two positions against the trailing window definition
    r1 = o / o.shift(1) - 1.0
    for k in (360, 400):
        expect = r1.iloc[k - 359:k + 1].std(ddof=1)
        assert np.isfinite(s.iloc[k])
        assert abs(s.iloc[k] - expect) < 1e-12
    # changing the FUTURE must not move sigma at t
    o2 = o.copy()
    o2.iloc[450:] *= 1.5
    s2 = M.sigma_series(o2)
    assert abs(s2.iloc[400] - s.iloc[400]) < 1e-12
    # changing the PAST must move it (sanity the test can detect leakage)
    o3 = o.copy()
    o3.iloc[399] *= 1.5
    s3 = M.sigma_series(o3)
    assert abs(s3.iloc[400] - s.iloc[400]) > 1e-9


def test_sigma_warmup_and_forward_tail_truncation():
    o = _toy_opens(n=500)
    s = M.sigma_series(o)
    # min_periods=120 on r1 (whose first value is NaN): first valid at pos 120
    assert s.iloc[:120].isna().all()
    assert np.isfinite(s.iloc[120])
    # timestamp forward lookup: last h bars have no t+h in history -> NaN
    h = 6
    times = o.index
    oh = o.reindex(times + h * pd.Timedelta(hours=4)).to_numpy()
    assert np.isnan(oh[-h:]).all()
    assert np.isfinite(oh[:-h]).all()
    # y is NaN wherever sigma is NaN (warmup) by construction rule
    fwd = oh / o.to_numpy() - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        y = fwd / s.to_numpy()
    y[(~np.isfinite(s.to_numpy())) | (s.to_numpy() <= 0) | (~np.isfinite(fwd))] = np.nan
    assert np.isnan(y[:120]).all()
    assert np.isfinite(y[120])


def test_spearman_hand_checked():
    ic, n = M.spearman_xy([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    assert n == 4 and abs(ic - 1.0) < 1e-12
    ic, _ = M.spearman_xy([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0])
    assert abs(ic + 1.0) < 1e-12
    # ties get average ranks: pred ties vs strictly increasing target
    ic, _ = M.spearman_xy([1.0, 1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0])
    assert np.isfinite(ic) and 0.9 < ic < 1.0
    # constant side -> NaN; too few points -> NaN
    ic, n = M.spearman_xy([5.0, 5.0, 5.0, 5.0], [1.0, 2.0, 3.0, 4.0])
    assert np.isnan(ic) and n == 4
    ic, n = M.spearman_xy([1.0, 2.0], [1.0, 2.0])
    assert np.isnan(ic) and n == 2
    # NaNs are dropped pairwise
    ic, n = M.spearman_xy([1.0, np.nan, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    assert n == 3 and abs(ic - 1.0) < 1e-12


def test_xs_hand_checked():
    Pv = np.array([[1.0, 2.0, 3.0, 4.0],
                   [4.0, 3.0, 2.0, 1.0],
                   [7.0, 7.0, 7.0, 7.0],   # constant pred -> NaN
                   [1.0, np.nan, np.nan, np.nan]])  # <3 valid -> NaN
    Yv = np.array([[10.0, 20.0, 30.0, 40.0],
                   [10.0, 20.0, 30.0, 40.0],
                   [10.0, 20.0, 30.0, 40.0],
                   [10.0, 20.0, 30.0, 40.0]])
    xs = M.xs_point(Pv, Yv)
    assert abs(xs[0] - 1.0) < 1e-12
    assert abs(xs[1] + 1.0) < 1e-12
    assert np.isnan(xs[2])
    assert np.isnan(xs[3])


def test_bootstrap_guard_and_shape():
    rng = np.random.default_rng(7)
    # fewer valid positions than block length -> None (no CI claimed)
    assert M.boot_corr(np.arange(4.0), np.arange(4.0) ** 2, np.arange(4), 6, 50, rng) is None
    # well-behaved monotone data -> CI around a positive point
    x = np.repeat(np.arange(60.0), 1)
    y = x * 2.0 + np.sin(x)
    ci = M.boot_corr(x, y, np.arange(60), 6, 100, rng)
    assert ci is not None and len(ci) == 2 and ci[0] <= ci[1] and ci[0] > 0.9
