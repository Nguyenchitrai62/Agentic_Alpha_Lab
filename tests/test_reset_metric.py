"""Unit tests for research/diagnostics/r2_decompose5/reset_metric.py::year_reset.

Synthetic equity paths only (no market data). year_reset gives the metric for
a user starting the year with fresh capital: the four phase sub-accounts are
each renormalized by their own value at the anchor (1/4 weight each), then
averaged. R = 100*(es_end**(1/12)-1), DD = 100*max(1 - ms/pk) with
pk = running peak of the averaged close equity (no leading 1.0).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "research/diagnostics/r2_decompose5/reset_metric.py"


def _load_reset():
    spec = importlib.util.spec_from_file_location("reset_metric_under_test", RESET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")


def _grid(g1):
    return pd.date_range(G0, g1, freq="1h")


def _mk(grid, eq, eq_min=None):
    t = [str(x) for x in grid]
    eq = list(eq)
    mn = list(eq_min) if eq_min is not None else list(eq)
    return {"t": t, "eq": eq, "eq_min": mn}


def _runs(grid, per_phase, strat="S"):
    return {s: {strat: _mk(grid, *per_phase[s])} for s in range(4)}


def test_flat_paths_give_zero_return_and_zero_dd():
    rm = _load_reset()
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    g1 = a0 + pd.Timedelta(days=365)
    grid = _grid(g1)
    runs = _runs(grid, [([1.0] * len(grid),) for _ in range(4)])
    out = rm.year_reset(runs, "S", 0, g1=g1)
    assert out == {"R": 0.0, "DD": 0.0}


def test_hand_computed_growth_12pct():
    rm = _load_reset()
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    g1 = a0 + pd.Timedelta(days=365)
    grid = _grid(g1)
    eq = [1.0] * len(grid)
    eq[-1] = 1.12
    runs = _runs(grid, [(eq,) for _ in range(4)])
    out = rm.year_reset(runs, "S", 0, g1=g1)
    assert out["R"] == round(100 * (1.12 ** (1 / 12) - 1), 3) == 0.949
    assert out["DD"] == 0.0


def test_conservative_intrabar_dd_averages_dip():
    # Close equity flat 1.0 everywhere; one phase has eq_min 0.8 intraday.
    # ms dips to (0.8+1+1+1)/4 = 0.95 while pk stays 1.0 -> DD 5.0.
    rm = _load_reset()
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    g1 = a0 + pd.Timedelta(days=365)
    grid = _grid(g1)
    one = [1.0] * len(grid)
    dip = [0.8] * len(grid)
    runs = {
        0: {"S": _mk(grid, one, dip)},
        1: {"S": _mk(grid, one)},
        2: {"S": _mk(grid, one)},
        3: {"S": _mk(grid, one)},
    }
    out = rm.year_reset(runs, "S", 0, g1=g1)
    assert out["R"] == 0.0
    assert out["DD"] == 5.0


def test_dominant_phase_reset_to_quarter_each_year():
    # Phase 0 doubles in year 0 (1->2) then doubles again in year 1 (2->4);
    # others flat. Reset re-weights to 1/4 at each anchor, so year-1 end is
    # (2.0+1+1+1)/4 = 1.25 -> R 1.877. A continuous mix would end at
    # 1.75/1.25 = 1.4x -> R 2.844 (see test_phase_mix.py).
    rm = _load_reset()
    a1 = pd.Timestamp("2022-09-24", tz="UTC")
    g1 = pd.Timestamp("2023-09-24", tz="UTC") + pd.Timedelta(days=365) - pd.Timedelta(days=365)
    g1 = pd.Timestamp("2023-09-24", tz="UTC")
    grid = _grid(g1 + pd.Timedelta(hours=1))
    m0 = pd.Timestamp("2022-03-24", tz="UTC")
    m1 = pd.Timestamp("2023-03-24", tz="UTC")
    eq0 = [1.0 if x < m0 else (2.0 if x < m1 else 4.0) for x in grid]
    eqf = [1.0] * len(grid)
    runs = {s: {"S": _mk(grid, eq0 if s == 0 else eqf)} for s in range(4)}
    y0 = rm.year_reset(runs, "S", 0, g1=g1 + pd.Timedelta(hours=1))
    assert y0["R"] == round(100 * (1.25 ** (1 / 12) - 1), 3) == 1.877
    y1 = rm.year_reset(runs, "S", 1, g1=g1 + pd.Timedelta(hours=1))
    assert y1["R"] == 1.877
    assert y1["DD"] == 0.0
    # And a flat year after the doubling resets to exactly 1.0 -> R 0.
    a2 = pd.Timestamp("2023-09-24", tz="UTC")
    grid2 = _grid(a2)
    eq0b = [1.0 if x < m0 else 2.0 for x in grid2]
    runs2 = {s: {"S": _mk(grid2, eq0b if s == 0 else [1.0] * len(grid2))} for s in range(4)}
    y1flat = rm.year_reset(runs2, "S", 1, g1=a2)
    assert y1flat == {"R": 0.0, "DD": 0.0}


def test_anchor_boundaries_base_uses_last_at_or_before_anchor():
    # y=1 anchor A1: value exactly at A1 is the base (<=), first point after
    # A1 starts the segment (>), endpoint A1+365d included, later excluded.
    rm = _load_reset()
    v388 = rm.v388
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    g1 = a1 + pd.Timedelta(days=365) + pd.Timedelta(hours=2)
    grid = _grid(g1)
    eq = []
    for x in grid:
        if x <= a1:
            eq.append(1.0)
        elif x <= a1 + pd.Timedelta(days=365):
            eq.append(2.0)
        else:
            eq.append(99.0)  # must be excluded from the year segment
    runs = _runs(grid, [(eq,) for _ in range(4)])
    out = rm.year_reset(runs, "S", 1, g1=g1)
    # es_end = 2.0/1.0 -> monthly 5.946
    assert out["R"] == round(100 * (2.0 ** (1 / 12) - 1), 3) == 5.946
    assert out["DD"] == 0.0


def test_no_history_before_anchor_falls_back_to_one():
    # y=0 anchor 2021-09-24 00:00 is before the hourly grid start
    # (2021-09-24 04:00), so b falls back to 1.0.
    rm = _load_reset()
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    assert a0 < G0
    g1 = a0 + pd.Timedelta(days=10)
    grid = _grid(g1)
    eq = [3.0] * len(grid)  # level 3 throughout -> 3x from base 1.0
    runs = _runs(grid, [(eq,) for _ in range(4)])
    out = rm.year_reset(runs, "S", 0, g1=g1)
    assert out["R"] == round(100 * (3.0 ** (1 / 12) - 1), 3)
