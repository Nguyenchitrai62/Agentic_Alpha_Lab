"""Tests for oc_blendsens (PLAN.md causality / alignment checks). Light: 4h parquets only."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_blendsens"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)


def _load_compute():
    spec = importlib.util.spec_from_file_location(
        "oc_blendsens_compute", HERE / "compute_blendsens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_blend_math():
    mod = _load_compute()
    o1u, dmeanu = mod.rebuild_legs()
    # Independent d2 formula (same files, same math as oc_dvolshort).
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    d2 = 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2
    dep = 0.8 * o1u + 0.2 * dmeanu
    common = dep.index.intersection(d2.index)
    pd.testing.assert_frame_equal(
        dep.reindex(common), d2.reindex(common), check_exact=True)
    # Convex mixes and extremes.
    pd.testing.assert_frame_equal(1.0 * o1u + 0.0 * dmeanu, o1u, check_exact=True)
    pd.testing.assert_frame_equal(0.0 * o1u + 1.0 * dmeanu, dmeanu, check_exact=True)
    a09 = 0.9 * o1u + 0.1 * dmeanu
    assert float((a09 - (0.5 * (0.8 * o1u + 0.2 * dmeanu)
                         + 0.5 * (1.0 * o1u + 0.0 * dmeanu))).abs().max().max()) < 1e-12


def test_bear_filter_exact():
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    panel = pd.read_parquet(HERE / "panel.parquet")
    grid = pd.DatetimeIndex(pd.to_datetime(panel["T"].unique(), utc=True)).sort_values()
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).fillna(False).reindex(grid).fillna(False)
    assert bear.isna().sum() == 0
    # Raw deployed blend vs panel filtered weights: longs halved exactly in bear.
    mod = _load_compute()
    o1u, dmeanu = mod.rebuild_legs()
    raw08 = (0.8 * o1u + 0.2 * dmeanu).reindex(grid).sort_index()
    for s in SYMS:
        wraw = raw08[s].to_numpy(float)
        bear_arr = bear.to_numpy(bool)
        expect = np.where(bear_arr & (wraw > 0), wraw * 0.5, wraw)
        got = panel[panel["sym"] == s].sort_values("T")[f"w_a08"].to_numpy(float)
        np.testing.assert_allclose(got, expect, rtol=0, atol=1e-12)
        # Shorts bit-identical to raw (parquet round-trip tolerance).
        neg = wraw < 0
        np.testing.assert_allclose(got[neg], wraw[neg], rtol=0, atol=1e-12)


def test_grid_bounds():
    panel = pd.read_parquet(HERE / "panel.parquet")
    T = pd.to_datetime(panel["T"], utc=True)
    assert bool((T < CUTOFF).all())
    assert int(T.min().value) >= int(ANCHORS[0].value)
    grid = pd.DatetimeIndex(pd.to_datetime(panel["T"].unique(), utc=True)).sort_values()
    bounds = ANCHORS + [LAST_BOUND]
    counts = [int(((grid >= bounds[k]) & (grid < bounds[k + 1])).sum()) for k in range(5)]
    assert sum(counts) == len(grid) and all(c > 2000 for c in counts)
    # Last bar has a forward open at/before CUTOFF.
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    assert bool((grid.max() + pd.Timedelta(hours=4) <= CUTOFF))
    assert bool(opens_full.reindex([grid.max() + pd.Timedelta(hours=4)]).notna().any(axis=1).all())


def test_cost_math():
    panel = pd.read_parquet(HERE / "panel.parquet")
    for name in ("O1", "a09", "a08", "a07", "D"):
        for s in SYMS:
            sub = panel[panel["sym"] == s].sort_values("T")
            w = sub[f"w_{name}"].to_numpy(float)
            prev = np.concatenate([[0.0], w[:-1]])
            expect = 0.0005 * np.abs(w - prev)
            np.testing.assert_allclose(
                sub[f"cost_{name}"].to_numpy(float), expect, rtol=0, atol=1e-12)
            # First grid bar prev = 0.
            assert abs(sub[f"cost_{name}"].to_numpy(float)[0]
                       - 0.0005 * abs(w[0])) < 1e-12
            # Net cell identity.
            np.testing.assert_allclose(
                sub[f"pnl_{name}"].to_numpy(float),
                w * sub["r1"].to_numpy(float) - expect, rtol=0, atol=1e-12)
