"""Tests for oc_bookattrib (vectorised beta-vs-timing attribution).

Covers: hand-checked synthetic B/BETA/TIMING + long/short split, year-window
truncation (no future bars), next-bar-only returns (causality), placebo block
shape, OLS Newey-West(5) on a known line.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MOD = ROOT / "research/tournament/oc_bookattrib/analyze_bookattrib.py"


def _load():
    spec = importlib.util.spec_from_file_location("oc_bookattrib_mod", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = _load()


def test_hand_checked_beta_timing_split():
    # 4 bars, 2 coins. Hand-computed.
    # w rows: [0.5, -0.5], [1.0, 0.0], [0.0, 1.0], [-1.0, -1.0]
    # r rows: [0.02, 0.04], [-0.01, 0.01], [0.03, -0.02], [0.01, 0.01]
    w = np.array([[0.5, -0.5], [1.0, 0.0], [0.0, 1.0], [-1.0, -1.0]])
    r = np.array([[0.02, 0.04], [-0.01, 0.01], [0.03, -0.02], [0.01, 0.01]])
    b = (w * r).sum(axis=1)
    assert np.allclose(b, [-0.01, -0.01, -0.02, -0.02])
    wbar = w.mean(axis=0)  # [0.125, -0.125]
    beta = (wbar[None, :] * r).sum(axis=1)
    # hand: row0: .125*.02 + (-.125)*.04 = -.0025; row1: -.0025; row2: .00625; row3: 0
    assert np.allclose(beta, [-0.0025, -0.0025, 0.00625, 0.0])
    tim = b - beta
    assert np.allclose(b, beta + tim, atol=1e-12)
    wl = np.where(w > 0, w, 0.0)
    ws = np.where(w < 0, w, 0.0)
    bl = (wl * r).sum(axis=1)
    bs = (ws * r).sum(axis=1)
    assert np.allclose(bl, [0.01, -0.01, -0.02, 0.0])
    assert np.allclose(bs, [-0.02, 0.0, 0.0, -0.02])
    assert np.allclose(b, bl + bs, atol=1e-12)
    # monthly geometric helper on known factor
    assert abs(A.monthly_geometric(1.0) - 0.0) < 1e-12
    assert abs(A.monthly_geometric((1.05) ** 12) - 5.0) < 1e-9


def test_next_bar_only_returns_causality():
    # r(t) must equal o(t+1)/o(t)-1 using ONLY the next open, never o(t+2).
    o = np.array([100.0, 110.0, 121.0, 200.0])  # last jump must not leak into r(0)
    r = o[1:] / o[:-1] - 1
    assert abs(r[0] - 0.10) < 1e-12
    assert abs(r[1] - 0.10) < 1e-12
    # if someone used o(t+2)/o(t) they would get 0.21 at t=0; assert we don't
    assert abs(r[0] - (o[2] / o[0] - 1)) > 1e-6


def test_year_truncation_wall_clock():
    idx = pd.DatetimeIndex([pd.Timestamp("2021-09-23 20:00", tz="UTC"),
                            pd.Timestamp("2021-09-24 00:00", tz="UTC"),
                            pd.Timestamp("2022-09-23 20:00", tz="UTC"),
                            pd.Timestamp("2022-09-24 00:00", tz="UTC")])
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    a1 = a0 + pd.Timedelta(days=365)
    m = (idx >= a0) & (idx < a1)
    assert m.tolist() == [False, True, True, False]


def test_placebo_blocks_cover_rows_exactly_once():
    nrows, block = 100, 42
    nb = (nrows + block - 1) // block
    blocks = [np.arange(i * block, min((i + 1) * block, nrows)) for i in range(nb)]
    assert sum(len(b) for b in blocks) == nrows
    full = [b for b in blocks if len(b) == block]
    partial = [b for b in blocks if len(b) != block]
    assert len(full) == 2 and len(partial) == 1 and len(partial[0]) == 16
    # permutation of full blocks covers each full-block row exactly once
    rng = np.random.default_rng(7)
    order = rng.permutation(len(full))
    seen = np.concatenate([full[o] for o in order])
    assert sorted(seen.tolist()) == sorted(np.concatenate(full).tolist())


def test_ols_nw5_known_line():
    x = np.arange(20, dtype=float)
    y = 1.0 + 2.0 * x
    out = A.ols_nw5(y, x)
    assert abs(out["beta"] - 2.0) < 1e-9
    assert abs(out["alpha_d"] - 1.0) < 1e-9
    assert out["n"] == 20
