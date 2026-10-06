"""Tests for oc_bookbrake (idea #17). No outcome tuning; causality + math checks."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_bookbrake"))
import compute_bookbrake as bb


def _syn(idx_hours, wmap, rmap):
    idx = pd.DatetimeIndex([pd.Timestamp("2022-01-01", tz="UTC") + pd.Timedelta(hours=h)
                            for h in idx_hours])
    w = pd.DataFrame({s: np.zeros(len(idx)) for s in bb.SYMS}, index=idx)
    r = pd.DataFrame({s: np.zeros(len(idx)) for s in bb.SYMS}, index=idx)
    for s, v in wmap.items():
        w[s] = np.asarray(v, dtype=float)
    for s, v in rmap.items():
        r[s] = np.asarray(v, dtype=float)
    return w, r


def test_trade_split_and_flip_cost_partition():
    # 4h grid of 6 bars; BTC: flat, long 2 bars, flat, short 1 bar, flat
    hrs = [0, 4, 8, 12, 16, 20]
    w, r = _syn(hrs, {"BTCUSDT": [0.0, 0.1, 0.15, 0.0, -0.1, 0.0]},
                {"BTCUSDT": [0.0, 0.01, -0.5, 0.0, -0.2, 0.0]})
    trades, closes = bb.segment_trades(w, r)
    btc = [t for t in trades if t["coin"] == "BTCUSDT"]
    assert len(btc) == 2
    assert (btc[0]["a"], btc[0]["b"]) == (1, 2)
    assert (btc[1]["a"], btc[1]["b"]) == (4, 4)
    # hand-check trade 1: gross = .1*.01 + .15*(-.5) = -0.074; cost=.0005*(.1+.05+.15)=.00015
    assert btc[0]["gross"] == round(0.1 * 0.01 + 0.15 * -0.5, 8)
    assert btc[0]["net"] == round(btc[0]["gross"] - 0.0005 * 0.3, 8)
    assert btc[0]["loss"] is True
    # trade costs partition the vectorised turnover exactly here
    to = w["BTCUSDT"].diff().abs().fillna(w["BTCUSDT"].abs()).sum()
    tcost = 0.1 + 0.05 + 0.15 + 0.1 + 0.1
    assert to == round(tcost, 12)
    # closures: trade1 -> open of bar 3; trade2 -> open of bar 5
    assert btc[0]["close_t"] == str(w.index[3])
    assert btc[1]["close_t"] == str(w.index[5])


def test_brake_trigger_and_window_edges():
    hrs = [0, 4, 8, 12, 16, 20, 24, 28]
    idx = pd.DatetimeIndex([pd.Timestamp("2022-01-01", tz="UTC") + pd.Timedelta(hours=h)
                            for h in hrs])
    # 3 loss closures at h=4,8,12; bar T=h=16 sees all 3 in [T-72h,T) -> brake on
    closes = pd.DatetimeIndex([idx[1], idx[2], idx[3]])
    scale = bb.brake_scale(idx, closes)
    assert float(scale.iloc[4]) == 0.5  # T=16h
    # closure exactly at T is strictly-before-excluded: drop the h=12 close...
    closes2 = pd.DatetimeIndex([idx[1], idx[2]])  # only 2 strictly before h=12
    scale2 = bb.brake_scale(idx, closes2)
    assert float(scale2.iloc[3]) == 1.0  # T=12h sees only 2
    # old closures fall out: at T=12+72h+4h only closes within window count
    idx2 = pd.DatetimeIndex([pd.Timestamp("2022-01-01", tz="UTC") + pd.Timedelta(hours=h)
                             for h in range(0, 200, 4)])
    closes3 = pd.DatetimeIndex([idx2[1], idx2[2], idx2[3]])  # hours 4, 8, 12
    s3 = bb.brake_scale(idx2, closes3)
    assert float(s3.iloc[19]) == 0.5  # T=76h: window [4,76) holds all 3 closes
    assert float(s3.iloc[20]) == 1.0  # T=80h: window [8,80) holds only 2


def test_brake_causal_on_real_grid():
    w, r = bb.load_grid()
    grid = w.index
    scale_full = bb.brake_scale(grid, bb.segment_trades(w, r)[1])
    P = grid[len(grid) // 2]
    w2 = w.copy()
    w2.loc[grid >= P] = w2.loc[grid >= P] + 1.0  # perturb present/future only
    r2 = r.copy()
    r2.loc[grid >= P] = -r2.loc[grid >= P]
    _, closes2 = bb.segment_trades(w2, r2)
    scale2 = bb.brake_scale(grid, closes2)
    same = grid <= P
    pd.testing.assert_series_equal(scale_full[same], scale2[same])


def test_year_partition_covers_scored_bars_once():
    w, _ = bb.load_grid()
    grid = w.index
    masks = bb.year_masks(grid)
    total = np.zeros(len(grid), dtype=int)
    for _, ym in masks:
        total += ym.astype(int)
    assert bool((total == 1).all())
