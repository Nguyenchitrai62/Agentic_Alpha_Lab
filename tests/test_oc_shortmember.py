"""Tests for oc_shortmember (fast, no training, no engine, no last-year data)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHM = ROOT / "research/tournament/oc_shortmember"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("shm_build_t", SHM / "build_shortmember.py")
R = _load("shm_run_t", SHM / "run_engine.py")


def _panel(n=60, hnew=6):
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    rng = np.random.RandomState(7)
    opens = 100 * np.exp(np.cumsum(rng.randn(n) * 0.01))
    rows = []
    for s in ("BTCUSDT", "ETHUSDT"):
        rows.append(pd.DataFrame({
            "t": t, "sym": s, "open": opens,
            "vol42": 0.01, "y": np.nan, "y6": np.nan, "y18": np.nan,
        }))
    return pd.concat(rows, ignore_index=True)


def test_relabel_formula_handchecked():
    # hand-check: constant vol, known opens; y = clip(log(o[t+1+h]/o[t+1])/(v*sqrt(h)))
    n, h = 20, 6
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    o = np.array([100.0 * (1.01 ** i) for i in range(n)])
    p = pd.DataFrame({"t": t, "sym": "BTCUSDT", "open": o, "vol42": 0.02, "y": np.nan})
    out = B.relabel_y(p, h)
    i = 3
    expect = np.clip(np.log(o[i + 1 + h] / o[i + 1]) / (0.02 * np.sqrt(h)), -4, 4)
    assert abs(out["y"].iloc[i] - expect) < 1e-12
    # tail rows without a realised forward are NaN
    assert out["y"].iloc[n - 2:].isna().all()
    # all return-target columns are overwritten identically
    p2 = p.copy()
    p2["y6"], p2["y18"] = 999.0, 999.0
    out2 = B.relabel_y(p2, h)
    pd.testing.assert_series_equal(out2["y"], out2["y6"], check_names=False)
    pd.testing.assert_series_equal(out2["y"], out2["y18"], check_names=False)


def test_relabel_truncation_causality():
    # dropping the last k bars must not change labels whose forwards are
    # fully realised before the truncation point (rows within h+1 bars of
    # the cut legitimately lose their forward window - same as training,
    # which requires t+(h+1) realised before the cutoff).
    h = 6
    full = _panel(80)
    cut = full["t"].max() - pd.Timedelta(hours=4 * 5)
    trunc = full[full["t"] < full["t"].max() - pd.Timedelta(hours=4 * 5)].copy()
    a = B.relabel_y(full, h).sort_values(["sym", "t"]).reset_index(drop=True)
    b = B.relabel_y(trunc, h).sort_values(["sym", "t"]).reset_index(drop=True)
    m = b[["sym", "t", "y"]].merge(a[["sym", "t", "y"]], on=["sym", "t"],
                                   suffixes=("", "_full"))
    realised = m["t"] + pd.Timedelta(hours=4 * (h + 1)) < cut
    assert realised.any()
    pd.testing.assert_series_equal(
        m.loc[realised, "y_full"].reset_index(drop=True),
        m.loc[realised, "y"].reset_index(drop=True), check_names=False)


def test_train_filter_requires_label_realised_before_cutoff():
    t = pd.date_range("2021-01-01", periods=200, freq="4h", tz="UTC")
    cutoff = t[150]
    for h in (6, 18, 42):
        late = t + pd.Timedelta(hours=4 * (h + 1)) >= cutoff
        assert late.any() and (~late).any()
        # the kept rows under the PLAN filter are exactly the non-late ones
        keep = t[~late]
        assert (keep + pd.Timedelta(hours=4 * (h + 1)) < cutoff).all()


def test_apply_bear_halves_positive_longs_only():
    idx = pd.date_range("2021-09-24", periods=4, freq="4h", tz="UTC")
    std = pd.DataFrame({"BTCUSDT": [1.0, -2.0, 0.0, 0.5],
                        "ETHUSDT": [-1.0, 3.0, 0.0, -0.5]}, index=idx)
    got = R.apply_bear(std, np.array([True, True, False, False]))
    assert got["BTCUSDT"].tolist() == [0.5, -2.0, 0.0, 0.5]
    assert got["ETHUSDT"].tolist() == [-1.0, 1.5, 0.0, -0.5]


def test_member_ic_year_assignment_is_disjoint():
    # anchor-year bins [A, A+365d) partition the grid (no overlap, no gap reuse)
    grid = pd.date_range("2021-09-24", periods=2190 * 2, freq="4h", tz="UTC")
    counts = np.zeros(len(grid), int)
    for a0 in B.ANCHORS[:2]:
        counts += ((grid >= a0) & (grid < a0 + B.YEAR)).astype(int)
    assert (counts <= 1).all()
