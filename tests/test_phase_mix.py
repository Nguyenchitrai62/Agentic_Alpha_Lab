"""Unit tests for v388 hourly / mix / year_stats with synthetic equity paths.

Covers hand-computed returns and DDs, a phase that dominates a continuous mix,
the conservative intrabar DD (mn vs close peak), and the anchor boundaries
(seg = (a0, a0+365d], base = last value <= a0).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V388 = ROOT / "research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py"


def _load():
    spec = importlib.util.spec_from_file_location("v388_under_test", V388)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(t, eq, eq_min=None):
    return {"t": list(t), "eq": list(eq), "eq_min": list(eq_min) if eq_min is not None else list(eq)}


def test_hourly_ffill_and_prefill_one():
    v388 = _load()
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    g1 = pd.Timestamp("2021-09-24 08:00", tz="UTC")
    run = _run(
        ["2021-09-24 04:00+00:00", "2021-09-24 06:00+00:00"],
        [1.0, 1.1],
    )
    e, mn = v388.hourly(run, g0, g1)
    assert list(e.index) == list(pd.date_range(g0, g1, freq="1h"))
    assert float(e.loc["2021-09-24 05:00+00:00"]) == 1.0  # ffill between sparse stamps
    assert float(e.loc["2021-09-24 06:00+00:00"]) == 1.1
    # no history before g0 -> fillna(1.0)
    run2 = _run(["2021-09-24 06:00+00:00"], [2.0])
    e2, _ = v388.hourly(run2, g0, g1)
    assert float(e2.loc["2021-09-24 04:00+00:00"]) == 1.0
    assert float(e2.loc["2021-09-24 06:00+00:00"]) == 2.0


def test_hourly_eqmin_shifted_4h_early_and_minimum():
    # eq flat 1.0; a single eq_min dip stamped at 08:00 must appear on the
    # grid from 04:00 (t - 4h), and mn = minimum(lo, e) everywhere.
    v388 = _load()
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    g1 = pd.Timestamp("2021-09-24 14:00", tz="UTC")
    run = _run(
        ["2021-09-24 04:00+00:00", "2021-09-24 08:00+00:00", "2021-09-24 12:00+00:00"],
        [1.0, 1.0, 1.0],
        [1.0, 0.8, 1.0],
    )
    e, mn = v388.hourly(run, g0, g1)
    assert (mn <= e).all()
    assert float(mn.loc["2021-09-24 04:00+00:00"]) == 0.8  # dip leads by 4h
    assert float(mn.loc["2021-09-24 07:00+00:00"]) == 0.8
    assert float(mn.loc["2021-09-24 08:00+00:00"]) == 1.0  # back to 1.0 at the stamp


def test_mix_averages_four_phases():
    v388 = _load()
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    g1 = pd.Timestamp("2021-09-24 06:00", tz="UTC")
    grid = pd.date_range(g0, g1, freq="1h")
    t = [str(x) for x in grid]
    allres = {
        0: {"S": _run(t, [2.0] * len(grid))},
        1: {"S": _run(t, [1.0] * len(grid))},
        2: {"S": _run(t, [1.0] * len(grid))},
        3: {"S": _run(t, [1.0] * len(grid))},
    }
    e, mn = v388.mix(allres, "S", g1)
    assert (e == 1.25).all()  # one dominating phase lifts the mix by 1/4 of its excess
    assert (mn == 1.25).all()


def test_dominant_phase_weighs_more_in_continuous_mix_than_reset():
    # Phase 0: 1->2 in year 0, 2->4 in year 1; others flat 1.
    # Continuous mix: start y1 = 1.25, end y1 = 1.75 -> net 40% -> R 2.844.
    # Reset (fresh 1/4 each year) would give 25% -> R 1.877 (see test_reset_metric).
    v388 = _load()
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    g1 = pd.Timestamp("2023-09-24", tz="UTC") + pd.Timedelta(hours=1)
    grid = pd.date_range(g0, g1, freq="1h")
    t = [str(x) for x in grid]
    m0 = pd.Timestamp("2022-03-24", tz="UTC")
    m1 = pd.Timestamp("2023-03-24", tz="UTC")
    eq0 = [1.0 if x < m0 else (2.0 if x < m1 else 4.0) for x in grid]
    eqf = [1.0] * len(grid)
    allres = {s: {"S": _run(t, eq0 if s == 0 else eqf)} for s in range(4)}
    e, mn = v388.mix(allres, "S", g1)
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    assert float(e[e.index <= a1].iloc[-1]) == 1.25
    y1 = v388.year_stats(e, mn, [1])
    assert y1["R"] == round(100 * (1.4 ** (1 / 12) - 1), 3) == 2.844
    assert y1["DD"] == 0.0
    assert y1["losing"] == 0


def test_year_stats_single_year_hand_computed():
    v388 = _load()
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    idx = pd.DatetimeIndex(
        [a1, a1 + pd.Timedelta(hours=1), a1 + pd.Timedelta(days=100), a1 + pd.Timedelta(days=365)]
    )
    e = pd.Series([1.0, 1.0, 1.06, 1.12], index=idx)
    mn = e.copy()
    out = v388.year_stats(e, mn, [1])
    assert out["R"] == round(100 * (1.12 ** (1 / 12) - 1), 3) == 0.949
    assert out["W"] == out["R"]
    assert out["DD"] == 0.0
    assert out["losing"] == 0


def test_year_stats_conservative_intrabar_dd():
    # Closes flat 1.0 (close-only DD would be 0) but one intrabar low 0.8
    # -> conservative DD 20.0.
    v388 = _load()
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    idx = pd.DatetimeIndex([a1] + list(pd.date_range(a1 + pd.Timedelta(hours=1), periods=5, freq="1h")))
    e = pd.Series([1.0] * len(idx), index=idx)
    mn = pd.Series([1.0] * len(idx), index=idx)
    mn.iloc[3] = 0.8
    out = v388.year_stats(e, mn, [1])
    assert out["R"] == 0.0
    assert out["DD"] == 20.0


def test_year_stats_immediate_drop_counts_from_one():
    # year_stats peaks from 1.0 (the reset base), so an immediate drop to
    # 0.5 is a 50% DD even though the year path itself is then flat.
    v388 = _load()
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    idx = pd.DatetimeIndex([a1, a1 + pd.Timedelta(hours=1), a1 + pd.Timedelta(days=365)])
    e = pd.Series([2.0, 1.0, 1.0], index=idx)
    mn = e.copy()
    out = v388.year_stats(e, mn, [1])
    assert out["R"] == round(100 * (0.5 ** (1 / 12) - 1), 3) == -5.613
    assert out["DD"] == 50.0
    assert out["losing"] == 1


def test_anchor_boundaries_exclude_anchor_include_endpoint():
    # Base = value AT the anchor (last <= a0); segment excludes a0 itself,
    # includes exactly a0+365d, excludes anything later.
    v388 = _load()
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    end = a1 + pd.Timedelta(days=365)
    idx = pd.DatetimeIndex(
        [
            a1 - pd.Timedelta(hours=1),
            a1,
            a1 + pd.Timedelta(hours=1),
            end - pd.Timedelta(hours=1),
            end,
            end + pd.Timedelta(hours=1),
        ]
    )
    e = pd.Series([1.0, 10.0, 2.0, 2.0, 3.0, 99.0], index=idx)
    out = v388.year_stats(e, e.copy(), [1])
    # segment = [2,2,3] / base 10 -> net -0.7
    assert out["R"] == round(100 * (0.3 ** (1 / 12) - 1), 3) == -9.546
    assert out["W"] == out["R"]
    assert out["DD"] == 80.0  # 1 - 0.2/1.0 from the leading 1.0 peak
    assert out["losing"] == 1


def test_year_stats_multiyear_geomean_worst_and_losing():
    # y0 net +25% (1->1.25), y1 net -20% (relative 1->0.8):
    # product 1.0 -> R 0.0; W = min monthly = monthly(-20%); losing = 1.
    v388 = _load()
    a0 = pd.Timestamp(v388.ANCH[0], tz="UTC")
    a1 = pd.Timestamp(v388.ANCH[1], tz="UTC")
    e0end = a0 + pd.Timedelta(days=365)
    e1end = a1 + pd.Timedelta(days=365)
    idx = pd.DatetimeIndex([a0, a0 + pd.Timedelta(hours=1), e0end, a1 + pd.Timedelta(hours=1), e1end])
    e = pd.Series([1.0, 1.0, 1.25, 1.25, 1.0], index=idx)
    mn = e.copy()
    out = v388.year_stats(e, mn, [0, 1])
    assert out["R"] == round(100 * ((1.25 * 0.8) ** (1 / 24) - 1), 3) == 0.0
    assert out["W"] == round(100 * (0.8 ** (1 / 12) - 1), 3) == -1.842
    assert out["losing"] == 1
    # flat year (net 0.0) is not losing
    out0 = v388.year_stats(e, mn, [0])
    assert out0["losing"] == 0
