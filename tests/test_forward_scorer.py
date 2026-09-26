"""Tests for scripts/forward_scorer.py. Synthetic log + prices only, no network."""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import forward_scorer as fs  # noqa: E402


def _grid(n, start="2026-01-01 00:00+00:00"):
    t0 = pd.Timestamp(start)
    return [t0 + i * pd.Timedelta(hours=4) for i in range(n)]


def _opens(grid, prices, sym="BTCUSDT"):
    return {sym: {t: p for t, p in zip(grid, prices)}}


def _dec(eff, perp, spot=None):
    return {"eff": eff, "perp": dict(perp), "spot": dict(spot or {})}


def test_extract_weights_formats():
    perp, spot = fs.extract_weights({"perp_weight": {"BTCUSDT": 0.5, "ETHUSDT": -0.1},
                                     "spot_weight": {"BTCUSDT": 0.2}})
    assert perp == {"BTCUSDT": 0.5, "ETHUSDT": -0.1}
    assert spot == {"BTCUSDT": 0.2}
    assert fs.extract_weights({"target_fraction": 0.325}) == ({"BTCUSDT": 0.325}, {})
    assert fs.extract_weights({"target_position": 1, "size_fraction_of_equity": 0.65}) == (
        {"BTCUSDT": 0.65}, {})
    assert fs.extract_weights({"target_position": -1, "size_fraction_of_equity": 0.5}) == (
        {"BTCUSDT": -0.5}, {})
    assert fs.extract_weights({"target_position": 0, "size_fraction_of_equity": 0.0}) == (
        {"BTCUSDT": 0.0}, {})
    assert fs.extract_weights({"close_4h": 1.0}) is None


def test_parse_decisions_filters_and_dedupes():
    rows = [
        {"candidate": "c", "decision_bar_close": "2026-01-01 03:59:59.999000+00:00",
         "target_fraction": 0.5, "logged_at": "2026-01-01T04:05:00+00:00", "mode": "prospective"},
        {"candidate": "c", "decision_bar_close": "2026-01-01 03:59:59.999000+00:00",
         "target_fraction": 0.7, "logged_at": "2026-01-01T04:06:00+00:00", "mode": "prospective"},
        {"candidate": "c", "decision_bar_close": "2026-01-01 07:59:59.999000+00:00",
         "target_fraction": 0.1, "logged_at": "2026-01-01T08:05:00+00:00", "mode": "backfill"},
        {"candidate": "u", "decision_bar_close": "2026-01-01 03:59:59.999000+00:00",
         "perp_weight": {"BTCUSDT": 0.1}, "note": "x UNGOVERNED y",
         "logged_at": "2026-01-01T04:05:00+00:00", "mode": "prospective"},
    ]
    out = fs.parse_decisions(rows)
    assert out["c"]["n_decisions"] == 1  # backfill ignored, dup close keeps last log
    assert out["c"]["decisions"][0]["perp"] == {"BTCUSDT": 0.7}
    assert out["c"]["decisions"][0]["eff"] == pd.Timestamp("2026-01-01 04:00+00:00")
    assert out["u"]["ungoverned"] is True
    assert out["c"]["ungoverned"] is False


def test_timing_no_fill_before_next_open():
    grid = _grid(3)
    closes = [t - pd.Timedelta(milliseconds=1) for t in grid[1:]]
    _ = closes
    perp = _opens(grid, [100.0, 110.0, 121.0])
    # Decided at close of bar0 -> effective at grid[1] open. The 100->110 move
    # must NOT count; only 110->121 (+10%) counts.
    decs = _dec(grid[1], {"BTCUSDT": 1.0}),
    res = fs.score_candidate(list(decs), grid, perp, {}, cost_rate=0.0, funding_per_bar=0.0)
    assert res["bars_held"] == 1
    assert res["cum_net_return_pct"] == pytest.approx(10.0)


def test_cost_arithmetic_entry_and_exit():
    grid = _grid(4)
    perp = _opens(grid, [100.0] * 4)
    decs = [_dec(grid[0], {"BTCUSDT": 1.0}), _dec(grid[2], {"BTCUSDT": 0.0})]
    res = fs.score_candidate(decs, grid, perp, {}, cost_rate=0.0002, funding_per_bar=0.0)
    assert res["bars_held"] == 3
    assert res["turnover"] == pytest.approx(2.0)
    assert res["cost_drag_pct"] == pytest.approx(0.04)
    assert res["cum_net_return_pct"] == pytest.approx((1 - 0.0002) ** 2 * 100 - 100)


def test_funding_long_pays_short_free():
    grid = _grid(5)
    perp = _opens(grid, [100.0] * 5)
    long = fs.score_candidate([_dec(grid[0], {"BTCUSDT": 1.0})], grid, perp, {},
                              cost_rate=0.0, funding_per_bar=0.00005)
    short = fs.score_candidate([_dec(grid[0], {"BTCUSDT": -1.0})], grid, perp, {},
                               cost_rate=0.0, funding_per_bar=0.00005)
    assert long["bars_held"] == 4
    assert long["funding_drag_pct"] == pytest.approx(0.02)
    assert long["cum_net_return_pct"] == pytest.approx((1 - 0.00005) ** 4 * 100 - 100)
    assert short["funding_drag_pct"] == pytest.approx(0.0)
    assert short["cum_net_return_pct"] == pytest.approx(0.0)


def test_gap_keeps_previous_weights():
    grid = _grid(5)
    perp = _opens(grid, [100.0, 101.0, 102.0, 103.0, 104.0])
    # Gap: decisions only at grid[0] (long) and grid[3] (flat); bars 1-2 held long.
    decs = [_dec(grid[0], {"BTCUSDT": 1.0}), _dec(grid[3], {"BTCUSDT": 0.0})]
    res = fs.score_candidate(decs, grid, perp, {}, cost_rate=0.0, funding_per_bar=0.0)
    assert res["bars_held"] == 4
    assert res["cum_net_return_pct"] == pytest.approx(3.0)


def test_spot_leg_scored_on_spot_opens():
    grid = _grid(3)
    perp = _opens(grid, [100.0] * 3)
    spot = {"BTCUSDT": {grid[0]: 50.0, grid[1]: 50.0, grid[2]: 55.0}}
    decs = [_dec(grid[1], {"BTCUSDT": 0.0}, {"BTCUSDT": 1.0})]
    res = fs.score_candidate(decs, grid, perp, spot, cost_rate=0.0, funding_per_bar=0.0)
    assert res["bars_held"] == 1
    assert res["cum_net_return_pct"] == pytest.approx(10.0)


def test_governor_multiplier_levels():
    assert fs.governor_multiplier(0.05) == 1.0
    assert fs.governor_multiplier(0.15) == pytest.approx(0.5)
    assert fs.governor_multiplier(0.20) == pytest.approx(0.0)
    assert fs.governor_multiplier(0.30) == pytest.approx(0.0)


def test_governor_freezes_after_deep_drawdown():
    grid = _grid(6)
    perp = _opens(grid, [100.0, 90.0, 80.0, 70.0, 60.0, 50.0])
    decs = [_dec(grid[0], {"BTCUSDT": 1.0})]
    raw = fs.score_candidate(decs, grid, perp, {}, cost_rate=0.0,
                             funding_per_bar=0.0, governed=False)
    gov = fs.score_candidate(decs, grid, perp, {}, cost_rate=0.0,
                             funding_per_bar=0.0, governed=True)
    assert gov["bars_held"] == raw["bars_held"] == 5
    assert gov["mean_g"] < 1.0
    # Governed path cuts exposure once DD passes 20%, so it loses less.
    assert gov["cum_net_return_pct"] > raw["cum_net_return_pct"]
    assert gov["max_drawdown_pct"] <= raw["max_drawdown_pct"]


def test_governor_first_two_bars_ungated():
    grid = _grid(4)
    perp = _opens(grid, [100.0, 50.0, 50.0, 50.0])
    decs = [_dec(grid[0], {"BTCUSDT": 1.0})]
    gov = fs.score_candidate(decs, grid, perp, {}, cost_rate=0.0,
                             funding_per_bar=0.0, governed=True)
    # Full -50% on bar 0 (g=1 for i<2), then g=0 freezes the path.
    assert gov["cum_net_return_pct"] == pytest.approx(-50.0)
    assert gov["turnover"] == pytest.approx(2.0)  # 0->1 entry, 1->0 governor cut


def test_trailing_unpriced_bar_skipped():
    grid = _grid(2)
    perp = _opens(grid, [100.0, 110.0])
    res = fs.score_candidate([_dec(grid[1], {"BTCUSDT": 1.0})], grid, perp, {},
                             cost_rate=0.0, funding_per_bar=0.0)
    assert res["bars_held"] == 0
    assert res["cum_net_return_pct"] == pytest.approx(0.0)
