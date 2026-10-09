"""Tests for oc_hlspread (PLAN-fixed signal). Light: synthetic + truncation only."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MOD = ROOT / "research" / "tournament" / "oc_hlspread" / "compute_panel.py"


def _load():
    spec = importlib.util.spec_from_file_location("hlspread_panel", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_handchecked_D_and_z():
    m = _load()
    # 8h windows every 8h from t0; grid 4h bars. D(T) = mean of last 21 settled.
    t0 = pd.Timestamp("2023-05-12 00:00", tz="UTC")
    wins = pd.date_range(t0, periods=30, freq="8h")
    win_ns = wins.values.astype("datetime64[ns]").astype(np.int64)
    draw = np.arange(30, dtype=float)  # 0..29
    grid = pd.date_range(t0, periods=60, freq="4h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)
    D = m.compute_D(grid_ns, win_ns, draw)
    # At T = t0+8h*21 (window 21 settled? w<=T-8h -> last window idx 20): mean 0..20
    T = t0 + pd.Timedelta(hours=8 * 21)
    i = int(np.searchsorted(grid_ns, T.value))
    assert grid[i] == T
    assert D[i] == np.mean(np.arange(21))
    # One 4h earlier: T-4h -> last settled window idx 19 (since w<=T-8h): mean 0..19 over last 21? needs idx>=20 -> NaN
    assert np.isnan(D[i - 1])  # only 20 windows settled -> NaN
    # z hand-check: constant D -> std 0 -> NaN; ramp -> finite after 720 bars
    D2 = np.arange(1000, dtype=float)
    g2 = pd.date_range("2023-01-01", periods=1000, freq="4h").values.astype("datetime64[ns]").astype(np.int64)
    z = m.compute_z(D2, g2)
    assert np.isnan(z[:720]).all()  # min 720 prior
    assert np.isfinite(z[721])  # first finite after enough history
    # constant series -> NaN (var==0)
    zc = m.compute_z(np.ones(1000), g2)
    assert np.isnan(zc).all()


def test_causality_truncation():
    m = _load()
    t0 = pd.Timestamp("2023-05-12 00:00", tz="UTC")
    wins = pd.date_range(t0, periods=400, freq="8h")
    win_ns = wins.values.astype("datetime64[ns]").astype(np.int64)
    rng = np.random.default_rng(0)
    draw = rng.normal(size=400)
    grid = pd.date_range(t0, periods=3000, freq="4h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)
    D = m.compute_D(grid_ns, win_ns, draw)
    z = m.compute_z(D, grid_ns)
    # truncate windows after cutoff: pre-cutoff D/z unchanged
    cut = pd.Timestamp("2024-01-01", tz="UTC").value
    keep = win_ns <= cut
    D2 = m.compute_D(grid_ns, win_ns[keep], draw[keep])
    pre = grid_ns < cut
    # D2 may be NaN where D used post-cutoff windows; but where D2 finite, equals D
    both = np.isfinite(D) & np.isfinite(D2) & pre
    assert both.sum() > 100
    assert np.allclose(D[both], D2[both])
    # z truncation: recompute z from D truncated to < T must match at sampled T
    for T in [pd.Timestamp("2024-06-01", tz="UTC").value, pd.Timestamp("2024-09-01", tz="UTC").value]:
        i = int(np.searchsorted(grid_ns, T))
        Dtr = D.copy()
        Dtr[grid_ns > grid_ns[i]] = np.nan  # hide strictly-future D (current kept)
        # compute z manually for row i from strictly prior D (same function on truncated grid)
        z2 = m.compute_z(Dtr[:i + 1], grid_ns[:i + 1])
        assert (np.isnan(z[i]) and np.isnan(z2[i])) or abs(z[i] - z2[i]) < 1e-12


def test_hl_8h_mixed_cadence():
    m = _load()
    # mixed 8h + hourly rows in one window sum together
    rows = pd.DataFrame({
        "time": pd.to_datetime(["2023-05-12 00:00", "2023-06-10 01:00", "2023-06-10 02:00",
                                "2023-06-10 07:00"], utc=True),
        "fundingRate": [0.001, 0.0001, 0.0002, 0.0003],
        "premium": [0.0] * 4,
    })
    out = m.hl_8h(rows)
    assert len(out) == 2
    assert abs(out["hl_sum"].iloc[0] - 0.001) < 1e-12
    assert abs(out["hl_sum"].iloc[1] - 0.0006) < 1e-12
