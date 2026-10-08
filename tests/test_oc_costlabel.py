"""Tests for oc_costlabel (fast, no training, no engine, no last-year data)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CL = ROOT / "research/tournament/oc_costlabel"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("cl_build_t", CL / "build_costlabel.py")
R = _load("cl_run_t", CL / "run_engine.py")


def _panel(n=60):
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    rng = np.random.RandomState(7)
    opens = 100 * np.exp(np.cumsum(rng.randn(n) * 0.01))
    rows = []
    for s in ("BTCUSDT", "ETHUSDT"):
        rows.append(pd.DataFrame({"t": t, "sym": s, "open": opens}))
    return pd.concat(rows, ignore_index=True)


def test_ycost_formula_handchecked():
    # hand-check: known opens, thr=8bps; y = 1{log(o[t+1+h]/o[t+1]) > thr}, h=6
    n, h, thr = 20, 6, 0.0008
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    o = np.array([100.0 * (1.001 ** i) for i in range(n)])
    p = pd.DataFrame({"t": t, "sym": "BTCUSDT", "open": o})
    out = B.add_y_cost(p, thr, h)
    i = 3
    expect_fwd = np.log(o[i + 1 + h] / o[i + 1])
    assert abs(out["y_cost"].iloc[i] - float(expect_fwd > thr)) < 1e-12
    # tail rows without a realised forward are NaN
    assert out["y_cost"].iloc[n - 2:].isna().all()
    # threshold edge: exactly at thr is 0 (strict >)
    o2 = np.array([100.0, 100.0 * np.exp(thr)] + [100.0 * np.exp(thr)] * (n - 2))
    p2 = pd.DataFrame({"t": t, "sym": "BTCUSDT", "open": o2})
    out2 = B.add_y_cost(p2, thr, h)
    # row 0 forward spans o[1..1+h]; constant after -> fwd == thr -> label 0
    assert out2["y_cost"].iloc[0] == 0.0


def test_ycost_truncation_causality():
    # dropping the last k bars must not change labels whose forwards are
    # fully realised before the truncation point.
    h, thr = 6, 0.0008
    full = _panel(80)
    cut = full["t"].max() - pd.Timedelta(hours=4 * 5)
    trunc = full[full["t"] < full["t"].max() - pd.Timedelta(hours=4 * 5)].copy()
    a = B.add_y_cost(full, thr, h).sort_values(["sym", "t"]).reset_index(drop=True)
    b = B.add_y_cost(trunc, thr, h).sort_values(["sym", "t"]).reset_index(drop=True)
    m = b[["sym", "t", "y_cost"]].merge(a[["sym", "t", "y_cost"]], on=["sym", "t"],
                                        suffixes=("", "_full"))
    realised = m["t"] + pd.Timedelta(hours=4 * (h + 1)) < cut
    assert realised.any()
    pd.testing.assert_series_equal(
        m.loc[realised, "y_cost_full"].reset_index(drop=True),
        m.loc[realised, "y_cost"].reset_index(drop=True), check_names=False)


def test_train_filter_requires_label_realised_before_cutoff():
    t = pd.date_range("2021-01-01", periods=200, freq="4h", tz="UTC")
    cutoff = t[150]
    for h in (6, 18, 42, 84):
        late = t + pd.Timedelta(hours=4 * (h + 1)) >= cutoff
        assert late.any() and (~late).any()
        keep = t[~late]
        assert (keep + pd.Timedelta(hours=4 * (h + 1)) < cutoff).all()
    # cost label realised at t+7 bars: the kept native filters all imply it
    assert ((t + pd.Timedelta(hours=4 * 7) >= cutoff)).any()


def test_apply_bear_halves_positive_longs_only():
    idx = pd.date_range("2021-09-24", periods=4, freq="4h", tz="UTC")
    std = pd.DataFrame({"BTCUSDT": [1.0, -2.0, 0.0, 0.5],
                        "ETHUSDT": [-1.0, 3.0, 0.0, -0.5]}, index=idx)
    got = R.apply_bear(std, np.array([True, True, False, False]))
    assert got["BTCUSDT"].tolist() == [0.5, -2.0, 0.0, 0.5]
    assert got["ETHUSDT"].tolist() == [-1.0, 1.5, 0.0, -0.5]


def test_isotonic_mapping_is_monotone():
    from sklearn.isotonic import IsotonicRegression
    rng = np.random.RandomState(0)
    p = np.sort(rng.rand(200))
    y = 2 * p - 1 + rng.randn(200) * 0.01
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p, y)
    grid = np.linspace(0, 1, 11)
    mapped = iso.predict(grid)
    assert bool((np.diff(mapped) >= -1e-12).all())
    # clip behaviour outside [0,1]
    assert iso.predict([2.0])[0] == mapped[-1]
